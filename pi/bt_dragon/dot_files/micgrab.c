/* micgrab: records a spoken question from the Echo Dot's microphones (runs ON the Dot).
 *
 * The Dot's microphone input (card 0, device 24) only accepts one format: 9 channels,
 * 16,000 samples a second, packed 24-bit (S24_3LE). Channels 1-7 are the microphones.
 * tinycap can't ask for packed 24-bit, so this small program talks to the sound driver
 * directly, with no C library at all (raw Linux system calls), so it runs on Fire OS as is.
 *
 *   micgrab OUT.wav [MAX_SECONDS] [GAIN]     record one question
 *   micgrab keys                             report the Dot's buttons, one line per press
 *   micgrab stream [GAIN]                    send the microphones, mixed, to the output for
 *                                            ever (raw 16-bit mono, 16 kHz), for the wake
 *                                            word; it ends when nobody's reading any more
 *
 * It mixes the 7 microphones into one channel (averaging them lowers the background hiss),
 * turns it into ordinary 16-bit mono WAV with GAIN (default 8 = +18 dB, as the microphones
 * are quiet), and stops by itself: after you stop talking (0.8 s of quiet once speech has
 * started), if nobody speaks within 4 seconds, or at MAX_SECONDS (default 8).
 * It prints SPEECH or SILENCE and the length, for the Pi to read.
 *
 * Built with:  clang -target armv7a-linux-gnueabi -mcpu=cortex-a53 -mfloat-abi=soft -marm -Os
 *              -ffreestanding -fno-builtin -fno-stack-protector -nostdlib -static
 *              -fuse-ld=lld -Wl,-e,_start -o micgrab micgrab.c
 * The voice-activity part (struct vad) is plain C and is also tested on a PC (tests/).
 */
typedef unsigned int u32;
typedef int s32;

/* ------------------------------------------------------------------ voice activity */
#define RATE 16000
#define BLOCK 256                     /* samples per decision: 16 ms */
struct vad {
    int noise;                        /* running background level (mean absolute value) */
    int blocks, loud_run, quiet_run, speech, done, why; /* why: 1 speech ended, 2 nobody spoke, 3 max time */
    int max_blocks;
};
static void vad_init(struct vad *v, int max_seconds) {
    v->noise = 0; v->blocks = v->loud_run = v->quiet_run = v->speech = v->done = v->why = 0;
    v->max_blocks = max_seconds * RATE / BLOCK;
}
/* feed one block of 16-bit samples; returns 1 when recording should stop.
 * Loudness is the block's average absolute sample value (32-bit maths only: the Dot's
 * library-free build has no 64-bit division). */
static int vad_feed(struct vad *v, const short *s, int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) sum += s[i] < 0 ? -s[i] : s[i];
    int lvl = n ? sum / n : 0;
    v->blocks++;
    if (v->blocks <= 12) {                       /* first ~0.2 s: learn the room's hiss */
        v->noise = v->blocks == 1 ? lvl : (v->noise * 3 + lvl) / 4;
        return 0;
    }
    int thr = v->noise * 5 / 2;                  /* about 8 dB above the background */
    if (thr < 160) thr = 160;                    /* never trigger on near-silence (about -46 dBFS) */
    if (lvl > thr) {
        v->loud_run++; v->quiet_run = 0;
        if (v->loud_run >= 4) v->speech = 1;     /* 64 ms of sound in a row = speech */
    } else {
        v->loud_run = 0; v->quiet_run++;
        if (!v->speech) v->noise = (v->noise * 15 + lvl) / 16;   /* keep learning the hiss */
    }
    if (v->speech && v->quiet_run >= 50) { v->done = 1; v->why = 1; }          /* 0.8 s quiet */
    else if (!v->speech && v->blocks >= 4 * RATE / BLOCK) { v->done = 1; v->why = 2; }
    else if (v->blocks >= v->max_blocks) { v->done = 1; v->why = 3; }
    return v->done;
}

#ifndef MICGRAB_HOST
/* ------------------------------------------------------------------ the Dot */
static long sys(long n, long a, long b, long c) {
    register long r0 __asm__("r0") = a, r1 __asm__("r1") = b, r2 __asm__("r2") = c, r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return r0;
}
#define SYS_exit 1
#define SYS_write 4
#define SYS_open 5
#define SYS_close 6
#define SYS_lseek 19
#define SYS_ioctl 54
#define SYS_read 3
#define SYS_poll 168

static unsigned long slen(const char *s) { unsigned long n = 0; while (s[n]) n++; return n; }
static void out(int fd, const char *s) { sys(SYS_write, fd, (long)s, slen(s)); }
static void num(int fd, long v) {
    char b[24]; int i = 23; int neg = v < 0; unsigned long u = neg ? -v : v;
    b[i] = 0; do { b[--i] = '0' + u % 10; u /= 10; } while (u);
    if (neg) b[--i] = '-';
    out(fd, b + i);
}
static long atoi_(const char *s) { long v = 0; while (*s >= '0' && *s <= '9') v = v * 10 + (*s++ - '0'); return v; }
static void die(const char *what, long err) { out(1, "ERROR "); out(1, what); out(1, " "); num(1, err); out(1, "\n"); sys(SYS_exit, 1, 0, 0); }
static void *mset(void *d, int c, unsigned long n) { unsigned char *p = d; while (n--) *p++ = c; return d; }

struct mask { u32 bits[8]; };
struct interval { u32 min, max, flags; };
struct hw_params {
    u32 flags;
    struct mask masks[3];
    struct mask mres[5];
    struct interval intervals[12];
    struct interval ires[9];
    u32 rmask, cmask, info, msbits, rate_num, rate_den;
    u32 fifo_size;
    unsigned char reserved[64];
};
struct xferi { s32 result; void *buf; u32 frames; };
#define HW_PARAMS  0xC25C4111u
#define PREPARE    0x00004140u
#define START      0x00004142u
#define DROP       0x00004143u
#define READI      0x800C4151u
enum { I_SAMPLE_BITS, I_FRAME_BITS, I_CHANNELS, I_RATE, I_PERIOD_TIME, I_PERIOD_SIZE,
       I_PERIOD_BYTES, I_PERIODS, I_BUFFER_TIME, I_BUFFER_SIZE, I_BUFFER_BYTES, I_TICK_TIME };
static void set_mask(struct hw_params *p, int m, int bit) {
    mset(&p->masks[m], 0, sizeof(struct mask));
    p->masks[m].bits[bit >> 5] = 1u << (bit & 31);
}
static void set_int(struct hw_params *p, int i, u32 v) {
    p->intervals[i].min = p->intervals[i].max = v;
    p->intervals[i].flags = 4;
}
static void put32(unsigned char *b, u32 v) { b[0] = v; b[1] = v >> 8; b[2] = v >> 16; b[3] = v >> 24; }
static void put16(unsigned char *b, u32 v) { b[0] = v; b[1] = v >> 8; }

#define CH 9
#define MICS 7
static unsigned char raw[BLOCK * CH * 3];
static short mono[BLOCK];

static long open_mics(void) {
    long fd = sys(SYS_open, (long)"/dev/snd/pcmC0D24c", 2, 0);
    if (fd < 0) die("open", fd);
    struct hw_params p;
    mset(&p, 0, sizeof p);
    for (int i = 0; i < 3; i++) mset(&p.masks[i], 0xff, sizeof(struct mask));
    for (int i = 0; i < 12; i++) { p.intervals[i].min = 0; p.intervals[i].max = ~0u; }
    p.rmask = ~0u; p.info = ~0u;
    set_mask(&p, 0, 3);           /* interleaved */
    set_mask(&p, 1, 32);          /* S24_3LE */
    set_mask(&p, 2, 0);
    set_int(&p, I_SAMPLE_BITS, 24);
    set_int(&p, I_FRAME_BITS, 24 * CH);
    set_int(&p, I_CHANNELS, CH);
    set_int(&p, I_RATE, RATE);
    set_int(&p, I_PERIOD_SIZE, BLOCK);
    set_int(&p, I_PERIODS, 8);
    long r = sys(SYS_ioctl, fd, HW_PARAMS, (long)&p);
    if (r < 0) die("hw_params", r);
    if ((r = sys(SYS_ioctl, fd, PREPARE, 0)) < 0) die("prepare", r);
    return fd;

}

/* one block from the microphones, mixed to mono 16-bit with gain; returns frames read */
static int read_block(long fd, int gain) {
    struct xferi x;
    x.result = 0; x.buf = raw; x.frames = BLOCK;
    long r = sys(SYS_ioctl, fd, READI, (long)&x);
    if (r < 0) {
        if (r == -32) { sys(SYS_ioctl, fd, PREPARE, 0); sys(SYS_ioctl, fd, START, 0); return 0; }
        die("read", r);
    }
    int n = x.result;
    for (int i = 0; i < n; i++) {
        long sum = 0;
        for (int c = 0; c < MICS; c++) {
            const unsigned char *b = raw + (i * CH + c) * 3;
            sum += (long)(b[0] | (b[1] << 8) | ((signed char)b[2] << 16));   /* 24-bit, signed */
        }
        long m = (sum / MICS) * gain / 256;        /* 24 -> 16 bit, with gain */
        if (m > 32767) m = 32767;
        if (m < -32768) m = -32768;
        mono[i] = (short)m;
    }
    return n;
}

/* ---- the wake word: the microphones, mixed, sent out for as long as someone's reading */
static int stream(int gain) {
    long fd = open_mics();
    long r = sys(SYS_ioctl, fd, START, 0);
    if (r < 0) die("start", r);
    while (1) {
        int n = read_block(fd, gain);
        if (n && sys(SYS_write, 1, (long)mono, n * 2) < 0) break;   /* the Pi stopped listening */
    }
    sys(SYS_ioctl, fd, DROP, 0);
    return 0;
}

/* ---- buttons: read the two input devices and print "KEY <name> <1 down|0 up>" at once
 * (written straight to the output, never held in a buffer, so the Pi hears it instantly) */
struct input_event { u32 sec, usec; unsigned short type, code; s32 value; };
struct pollfd { int fd; short events, revents; };
static int keys(void) {
    struct pollfd pf[2];
    pf[0].fd = sys(SYS_open, (long)"/dev/input/event1", 0, 0);   /* action, mute */
    pf[1].fd = sys(SYS_open, (long)"/dev/input/event2", 0, 0);   /* volume */
    if (pf[0].fd < 0 && pf[1].fd < 0) die("open buttons", pf[0].fd);
    pf[0].events = pf[1].events = 1;
    out(1, "READY\n");
    while (1) {
        pf[0].revents = pf[1].revents = 0;
        long r = sys(SYS_poll, (long)pf, 2, -1);
        if (r < 0) die("poll", r);
        for (int i = 0; i < 2; i++) {
            if (pf[i].fd < 0 || !(pf[i].revents & 1)) continue;
            struct input_event e;
            if (sys(SYS_read, pf[i].fd, (long)&e, sizeof e) != sizeof e) continue;
            if (e.type != 1 || e.value == 2) continue;          /* keys only; skip auto-repeat */
            const char *name = e.code == 138 ? "ACTION" : e.code == 113 ? "MUTE" :
                               e.code == 115 ? "VOLUP" : e.code == 114 ? "VOLDOWN" : 0;
            out(1, "KEY ");
            if (name) out(1, name); else num(1, e.code);
            out(1, e.value ? " 1\n" : " 0\n");
        }
    }
}

int cmain(long *sp) {
    int argc = (int)sp[0];
    char **argv = (char **)(sp + 1);
    if (argc >= 2 && argv[1][0] == 'k' && argv[1][1] == 'e' && argv[1][2] == 'y' && argv[1][3] == 's' && !argv[1][4])
        return keys();
    if (argc >= 2 && argv[1][0] == 's' && argv[1][1] == 't' && argv[1][2] == 'r' && argv[1][3] == 'e')
        return stream(argc > 2 ? atoi_(argv[2]) : 8);
    if (argc < 2) { out(1, "usage: micgrab OUT.wav [MAX_SECONDS] [GAIN]\n"); return 2; }
    int maxs = argc > 2 ? atoi_(argv[2]) : 8, gain = argc > 3 ? atoi_(argv[3]) : 8;
    if (maxs < 1 || maxs > 30) maxs = 8;
    if (gain < 1 || gain > 64) gain = 8;

    long fd = open_mics(), r;
    long wf = sys(SYS_open, (long)argv[1], 01 | 0100 | 01000, 0666);
    if (wf < 0) die("create", wf);
    unsigned char h[44];
    mset(h, 0, 44);
    sys(SYS_write, wf, (long)h, 44);              /* header written properly at the end */

    if ((r = sys(SYS_ioctl, fd, START, 0)) < 0) die("start", r);
    struct vad v;
    vad_init(&v, maxs);
    u32 frames = 0, spoke_at = 0;
    while (1) {
        int n = read_block(fd, gain);
        if (!n) continue;                          /* an overrun: carry on */
        sys(SYS_write, wf, (long)mono, n * 2);
        frames += n;
        int was = v.speech;
        if (vad_feed(&v, mono, n)) break;
        if (v.speech && !was) spoke_at = frames;
    }
    sys(SYS_ioctl, fd, DROP, 0);
    sys(SYS_close, fd, 0, 0);
    u32 data = frames * 2;
    h[0]='R';h[1]='I';h[2]='F';h[3]='F'; put32(h+4, 36 + data);
    h[8]='W';h[9]='A';h[10]='V';h[11]='E'; h[12]='f';h[13]='m';h[14]='t';h[15]=' ';
    put32(h+16, 16); put16(h+20, 1); put16(h+22, 1); put32(h+24, RATE);
    put32(h+28, RATE * 2); put16(h+32, 2); put16(h+34, 16);
    h[36]='d';h[37]='a';h[38]='t';h[39]='a'; put32(h+40, data);
    sys(SYS_lseek, wf, 0, 0);
    sys(SYS_write, wf, (long)h, 44);
    sys(SYS_close, wf, 0, 0);
    out(1, v.speech ? "SPEECH " : "SILENCE ");
    num(1, frames * 1000 / RATE);
    out(1, " ms\n");
    (void)spoke_at;
    return 0;
}

__attribute__((naked, noreturn)) void _start(void) {
    __asm__ volatile("mov r0, sp\n bl cmain\n mov r7, #1\n svc 0\n");
}
#endif
