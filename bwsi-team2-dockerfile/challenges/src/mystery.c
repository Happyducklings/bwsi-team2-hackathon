#include <stdio.h>
#include <string.h>

static void transform(char *buf, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        char c = buf[i];
        if (c >= 'a' && c <= 'z')
            buf[i] = (char)(((c - 'a' + 13) % 26) + 'a');
        else if (c >= 'A' && c <= 'Z')
            buf[i] = (char)(((c - 'A' + 13) % 26) + 'A');
        /* digits, '_' and '!' pass through untouched */
    }
}

int main(void)
{
    char flag[] = "HWM{1nv35t1g4t1v3_R3v3rs3r!}";
    size_t n = strlen(flag);

    transform(flag, n);
    printf("%s\n", flag);   /* also its own decryptor - run twice */
    return 0;
}
