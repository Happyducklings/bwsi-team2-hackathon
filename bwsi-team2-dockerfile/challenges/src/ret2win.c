#include <stdio.h>
#include <string.h>
#include <unistd.h>

void win(void) {
    char flag[64];
    FILE *f = fopen("flag.txt", "r");
    if (!f) {
        puts("flag.txt missing — put it next to the binary");
        return;
    }
    fgets(flag, sizeof flag, f);
    printf("%s", flag);
    fclose(f);
}

/* glibc removed gets() (unsafe-by-design) years ago, so it no longer links
 * on this image. This reproduces its exact behavior byte-for-byte -
 * read until newline/EOF with no bounds check - so the overflow is
 * unchanged. */
static void unsafe_gets(char *buf) {
    int c;
    char *p = buf;
    while ((c = getchar()) != '\n' && c != EOF) {
        *p++ = (char)c;
    }
    *p = '\0';
}

void vuln(void) {
    char buf[64];
    puts("Say something:");
    unsafe_gets(buf);      // deliberately vulnerable — no bounds check
    printf("You said: %s\n", buf);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    vuln();
    puts("Bye.");
    return 0;
}
