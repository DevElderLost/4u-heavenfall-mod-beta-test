@ Bootstrap of the extension: makes the extension's pages
@ executable before the game runs anything else.
@
@ The extension is the end of .data in an extended code.bin, so the system maps it read-write and
@ execute-never. The first instruction of the executable's entry (0x100000), `bl clear_bss`, is
@ replaced by `bl` to this block (code_space.Layout.extend). It runs once, before any other code:
@     svcDuplicateHandle(0xFFFF8001)                  a real handle of this process
@     svcFlushProcessDataCache(handle, ext, size)      the code bytes reach memory
@     svcControlProcessMemory(handle, ext, 0, size, MEMOP_PROT, R|X)
@     svcCloseHandle(handle)
@ and then goes on with the replaced call (clear_bss returns to the entry). The exheader allows these
@ calls (game/executable/exheader.py). Their results are ignored: an emulator that does not enforce
@ execute-never (Citra, Azahar) runs the extension either way. No instruction cache is invalidated:
@ the pages were never executed, and the stock kernel has no user call for it.
@ r0-r6 and lr are saved, so the entry sees the registers the system gave it.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ CURRENT_PROCESS, 0xFFFF8001
    .equ MEMOP_PROT, 6
    .equ PERMISSION_RX, 5

_start:
    push    {r0-r6, lr}
    ldr     r1, current_process
    svc     0x27                      @ DuplicateHandle: r0 result, r1 handle
    cmp     r0, #0
    bne     done
    mov     r6, r1
    ldr     r1, range_start
    ldr     r2, range_end
    sub     r2, r2, r1
    mov     r0, r6
    svc     0x54                      @ FlushProcessDataCache(handle, address, size)
    ldr     r1, range_start
    ldr     r3, range_end
    sub     r3, r3, r1
    mov     r0, r6
    mov     r2, #0
    mov     r4, #MEMOP_PROT
    mov     r5, #PERMISSION_RX
    svc     0x70                      @ ControlProcessMemory(handle, address, 0, size, type, permissions)
    mov     r0, r6
    svc     0x23                      @ CloseHandle(handle)
done:
    pop     {r0-r6, lr}
    b       clear_bss

current_process:
    .word   CURRENT_PROCESS
range_start:
    .word   ext_start
range_end:
    .word   ext_end
