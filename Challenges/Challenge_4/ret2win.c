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

void vuln(void) {
    char buf[64];
    puts("Say something:");
    gets(buf);            // deliberately vulnerable — no bounds check
    printf("You said: %s\n", buf);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    vuln();
    puts("Bye.");
    return 0;
}