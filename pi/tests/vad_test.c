/* Tests micgrab's "stop when you stop talking" logic on a PC: cc tests/vad_test.c -lm */
#define MICGRAB_HOST
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "../bt_dragon/dot_files/micgrab.c"
static int run(double speech_start, double speech_len, int maxs, double *stop) {
    struct vad v; vad_init(&v, maxs);
    short b[BLOCK]; srand(1);
    for (int blk = 0; ; blk++) {
        for (int i = 0; i < BLOCK; i++) {
            double t = (blk * BLOCK + i) / (double)RATE;
            double s = ((rand() % 201) - 100);                      /* room hiss */
            if (t >= speech_start && t < speech_start + speech_len)  /* a voice, wobbling in loudness */
                s += 1500 * sin(2 * M_PI * 220 * t) * (0.6 + 0.4 * sin(2 * M_PI * 3 * t));
            b[i] = (short)s;
        }
        if (vad_feed(&v, b, BLOCK)) { *stop = v.blocks * BLOCK / (double)RATE; return v.why; }
    }
}
int main(void) {
    double t1, t2, t3;
    int a = run(0.5, 2.0, 8, &t1);    /* speaks 0.5-2.5 s: stops about 0.8 s later */
    int b = run(99, 0, 8, &t2);       /* nobody speaks: gives up at 4 s */
    int c = run(0.5, 20, 8, &t3);     /* keeps talking: stops at 8 s */
    printf("speech ended -> stop %.2f s (why %d); silence -> %.2f s (why %d); long -> %.2f s (why %d)\n", t1, a, t2, b, t3, c);
    return !(a == 1 && t1 > 3.2 && t1 < 3.5 && b == 2 && c == 3 && t3 > 7.9);
}
