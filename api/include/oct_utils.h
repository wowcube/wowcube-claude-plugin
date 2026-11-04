// Public WowCube game API: generated from the engine sources (api/SOURCE).
// Only what a game compiled as a cube module (OCT_APP_MODULE) uses. Do not edit: regenerate.
#pragma once
//----------------------------------------------------------------------------------------------------
// Everything in this header can be included from any .c:
// - "static" makes it's own internal copy for each .c
// - "unused" silence warnings when some module isn't really using all functions
//----------------------------------------------------------------------------------------------------
#include <stdint.h>
#include <limits.h>


//This one is needed in FW compilation too
#ifdef __cplusplus
extern "C" {
#endif

//Supports only %d\%u (with %Nd width or %0Nd zero-padding), %s\%c and %%. Anything else is emitted literally
//and consumes NO argument, so every specifier after it reads the wrong one -- use OCT_text for anything richer.
//Returns the number of characters actually written excluding the trailing null
int OCT_snprintf(char* buf, size_t n, const char* fmt, ...)
{
    if (n == 0) return 0;
    va_list ap; va_start(ap, fmt);

    char* out = buf;
    char* end = buf + n - 1;                                                    //Last slot reserved for the null terminator
    #define OCT_PUT(c) do { if (out < end) *out++ = (char)(c); } while (0)

    while (*fmt) 
    {
        //Usual char
        if (*fmt != '%') { OCT_PUT(*fmt++); continue; }
        fmt++;

        //Parse width
        int zero_pad = 0;
        if (*fmt == '0') { zero_pad = 1; fmt++; }
        int width = 0;
        while (*fmt >= '0' && *fmt <= '9') width = width * 10 + (*fmt++ - '0');

        //Parse length modifier
        int len_l = 0, len_z = 0;
        if      (*fmt == 'l') { len_l = 1; fmt++; }
        else if (*fmt == 'z') { len_z = 1; fmt++; }

        //Process specificator
        switch (*fmt) 
        {
            case 'd': 
            {
                int32_t v = (len_l) ? (int32_t)va_arg(ap, long) : va_arg(ap, int);

                int neg = (v < 0);
                uint32_t u = neg ? (0u - (uint32_t)v) : (uint32_t)v;

                char d[12]; int k = 0;
                do { d[k++] = (char)('0' + u % 10); u /= 10; } while (u);

                int total = k + neg;
                if (zero_pad && neg)    OCT_PUT('-');                           //"-007": sign before zero-pad
                while (total++ < width) OCT_PUT(zero_pad ? '0' : ' ');
                if (!zero_pad && neg)   OCT_PUT('-');                           //"  -7": sign after space-pad
                while (k--)             OCT_PUT(d[k]);
                break;
            }

            case 'u':
            {
                uint32_t u;
                if      (len_z) u = (uint32_t)va_arg(ap, size_t);
                else if (len_l) u = (uint32_t)va_arg(ap, unsigned long);
                else            u = va_arg(ap, unsigned int);

                char d[12]; int k = 0;
                do { d[k++] = (char)('0' + u % 10); u /= 10; } while (u);

                int total = k;
                while (total++ < width) OCT_PUT(zero_pad ? '0' : ' ');
                while (k--)             OCT_PUT(d[k]);
                break;
            }

            case 'c':
            {
                char ch = (char)va_arg(ap, int);
                OCT_PUT(ch);
                break;
            }

            case 's': 
            {
                const char* s = va_arg(ap, const char*);
                if (!s) s = "(null)";
                while (*s) OCT_PUT(*s++);
                break;
            }

            case '%': OCT_PUT('%'); break;
            default:  OCT_PUT('%'); if (*fmt) OCT_PUT(*fmt); break;             //unknown spec: emit literally
        }
        if (*fmt) fmt++;
    }

    *out = '\0';
    #undef OCT_PUT
    va_end(ap);
    return (int)(out - buf);
}

#ifdef __cplusplus
}
#endif