; =============================================================================
;  Devtronix Organ Control System Loader, Revision C.04
;  Boot ROM of the Devtronix Model 264 pipe-organ relay  (Motorola 68000)
; =============================================================================
;
;  Annotated disassembly.  Not directly assemblable: addresses are shown on
;  the left, the raw words next, then an assembler-style rendering.
;  Mechanical reference: loader-c04.raw-sweep.txt (capstone linear sweep).
;
;  Source image : devtronix-hardware/devtronix-rom/devtronix.rom.merged
;                 with the two bytes of every 16-bit word swapped (mkrom.py).
;                 See README.md, "Byte order", for why.
;  ROM base     : $800000  (reset PC = $800008).
;  Relocation   : everything from $800038 on is copied to RAM at $07E000 and
;                 runs there.  Labels keep their ROM address; the running
;                 address is  ROM - $800038 + $07E000.  All control flow is
;                 PC-relative so the code is position independent.  The copy
;                 exists so that the cursor-address template at $800400 can be
;                 patched in place (ctl_gotoxy).
;
;  Register conventions
;    A4  console DUART channel base: $FFFFFE21 = channel A, $FFFFFE31 = channel B
;    D4  CSR (baud) codes; bit 16 set when the console was found on channel B
;    A2  sector buffer / string pointer      D2  logical sector number
;    D5  <> 0 when the disk is double sided  D3  file block index
;
;  I/O used (all byte wide, short absolute addressing, so $FFFFxxxx)
;    $FFFFFE00  write : two-digit status display (progress / error codes)
;    $FFFFFE03  read  : read once at reset, value discarded (purpose unknown)
;    $FFFFFE21.. MC68681 DUART, odd bytes:  +0 MR1A/MR2A  +2 SRA/CSRA  +4 CRA
;               +6 RHRA/THRA  +8 ACR  ;  channel B is the same at +$10
;    $FFFFFFE0  WD179x FDC command/status      $FFFFFFE2  FDC sector register
;    $FFFFFFE3  FDC data register (seek target) $FFFFFFE4  sector data port
;    $FFFFFFE5  write: clear INTRQ/DRQ latch   $FFFFFFE6  write: drive/side latch
;                                                          read : bit 1 = INTRQ
;    $FFFFFFE7  write: $80 = FDC run, $00 = FDC reset
;
; -----------------------------------------------------------------------------
;  Reset vectors
; -----------------------------------------------------------------------------
800000  0007F000              dc.l    $0007F000           ; initial SSP (top of RAM - 4 KB)
800004  00800008              dc.l    $00800008           ; initial PC

; -----------------------------------------------------------------------------
;  Reset: relocate the loader to RAM
; -----------------------------------------------------------------------------
800008  1E38 FE03     reset:  move.b  $FFFFFE03.w,d7      ; read I/O $FE03 (value unused)
80000C  11FC 0000 FE00        move.b  #$00,$FFFFFE00.w    ; display <- 00
800012  227C 0007E000         movea.l #$0007E000,a1       ; relocation target
800018  2449                  movea.l a1,a2
80001A  2C49                  movea.l a1,a6
80001C  3E3C 0200             move.w  #$200,d7
800020  421E          .clr:   clr.b   (a6)+               ; zero $7E000-$7E1FF (overwritten by the copy below)
800022  5347                  subq.w  #1,d7
800024  66FA                  bne.s   .clr
800026  47FA 0010             lea     main(pc),a3         ; $800038
80002A  323C 07D0             move.w  #2000,d1
80002E  24DB          .cpy:   move.l  (a3)+,(a2)+         ; copy 8000 bytes: ROM $800038.. -> RAM $7E000..
800030  5341                  subq.w  #1,d1               ;   (8000 bytes ~ a full 8 KB ROM; only 2 KB was dumped)
800032  66FA                  bne.s   .cpy
800034  2E49                  movea.l a1,a7               ; SP = $7E000, stack grows down below the code
800036  4ED1                  jmp     (a1)                ; continue at main, now in RAM

; -----------------------------------------------------------------------------
;  Main: find a console terminal by auto-baud, then prompt or auto-boot
; -----------------------------------------------------------------------------
800038  4EBA 02AC     main:   jsr     init_duart(pc)
80003C  283C 000066BB         move.l  #$66BB,d4           ; CSR codes: $BB = 9600 baud, $66 = 1200 baud
800042  11FC 00A1 FE00        move.b  #$A1,$FFFFFE00.w    ; display A1: probing channel A at 9600
800048  287C FFFFFE21         movea.l #$FFFFFE21,a4       ; A4 -> DUART channel A
80004E  183C 00BB             move.b  #$BB,d4
800052  4EBA 03BA             jsr     probe_console(pc)   ; ring BEL, wait for ESC
800056  6760                  beq.s   have_console
800058  08C4 0010             bset    #16,d4              ; remember: console is on channel B
80005C  E05C                  ror.w   #8,d4               ; d4.w = $BB66
80005E  287C FFFFFE31         movea.l #$FFFFFE31,a4       ; A4 -> DUART channel B
800064  11FC 00B1 FE00        move.b  #$B1,$FFFFFE00.w    ; display B1: channel B at 9600
80006A  183C 00BB             move.b  #$BB,d4
80006E  4EBA 039E             jsr     probe_console(pc)
800072  6744                  beq.s   have_console
800074  11FC 00B2 FE00        move.b  #$B2,$FFFFFE00.w    ; display B2: channel B at 2400
80007A  183C 0088             move.b  #$88,d4
80007E  4EBA 038E             jsr     probe_console(pc)
800082  6734                  beq.s   have_console
800084  11FC 00B3 FE00        move.b  #$B3,$FFFFFE00.w    ; display B3: channel B at 1200
80008A  183C 0066             move.b  #$66,d4
80008E  4EBA 037E             jsr     probe_console(pc)
800092  6724                  beq.s   have_console
;       nobody answered: talk to channel A anyway and boot without a prompt
800094  11FC 00C1 FE00        move.b  #$C1,$FFFFFE00.w    ; display C1: no console, auto-boot
80009A  287C FFFFFE21         movea.l #$FFFFFE21,a4
8000A0  283C 000066BB         move.l  #$66BB,d4
8000A6  45FA 0456             lea     msg_banner(pc),a2
8000AA  4EBA 02BA             jsr     puts(pc)
8000AE  45FA 048C             lea     msg_loading(pc),a2
8000B2  4EBA 02B2             jsr     puts(pc)
8000B6  602E                  bra.s   boot_disk

8000B8  7207          have_console:
                              moveq   #7,d1
8000BA  4EBA 02B8             jsr     putc(pc)            ; BEL
8000BE  45FA 043E             lea     msg_banner(pc),a2
8000C2  4EBA 02A2             jsr     puts(pc)
8000C6  45FA 0490             lea     msg_prompt(pc),a2   ; "Hit return to boot from disk: / Hit $ to download across modem:"
8000CA  4EBA 029A             jsr     puts(pc)
8000CE  4EBA 02B2     .key:   jsr     getc(pc)
8000D2  B23C 000D             cmp.b   #$0D,d1             ; CR  -> boot from floppy
8000D6  670E                  beq.s   boot_disk
8000D8  B23C 0024             cmp.b   #'$',d1             ; '$' -> download over the modem port
8000DC  6700 0186             beq.w   modem_download
8000E0  4EBA 0292             jsr     putc(pc)            ; anything else: echo it and wait again
8000E4  60E8                  bra.s   .key

; -----------------------------------------------------------------------------
;  Boot from floppy
; -----------------------------------------------------------------------------
8000E6  7207          boot_disk:
                              moveq   #7,d1
8000E8  4EBA 028A             jsr     putc(pc)            ; BEL
8000EC  247C 00040000         movea.l #$00040000,a2       ; sector buffer
8000F2  4282                  clr.l   d2                  ; logical sector 0 = boot block
8000F4  4285                  clr.l   d5                  ; assume single sided for the first read
8000F6  4EBA 00A4             jsr     read_sector(pc)
8000FA  0C2A 00F2 0001        cmpi.b  #$F2,1(a2)          ; boot block signature byte
800100  6620                  bne.s   raw_boot
800102  0812 0000             btst    #0,(a2)             ; byte 0 bit 0: disk is double sided
800106  56C5                  sne     d5
800108  4EBA 0036             jsr     load_monitor(pc)
80010C  6720                  beq.s   run_loaded
80010E  45FA 04AE             lea     msg_nomon(pc),a2    ; "?No system monitor on this disk"
800112  4EBA 0252             jsr     puts(pc)
800116  2E3C 0007A120         move.l  #500000,d7
80011C  5387          .dly:   subq.l  #1,d7
80011E  66FC                  bne.s   .dly
800120  6096                  bra.s   have_console        ; back to the prompt

;       Not a system disk: load logical sector 1 to address 0 and run it
800122  7401          raw_boot:
                              moveq   #1,d2
800124  95CA                  suba.l  a2,a2               ; a2 = 0
800126  204A                  movea.l a2,a0               ; entry = 0
800128  43FA 0072             lea     read_sector(pc),a1
80012C  4E91                  jsr     (a1)
;       a0 = entry point.  Leave console info for the loaded program:
;         $44.w = CSR codes (high byte channel B, low byte channel A)
;         $46.b = $FF when the console is on channel B
80012E  0804 0010     run_loaded:
                              btst    #16,d4
800132  6706                  beq.s   .a
800134  50F8 0046             st      $46.w
800138  E05C                  ror.w   #8,d4
80013A  31C4 0044     .a:     move.w  d4,$44.w
80013E  4ED0                  jmp     (a0)

; -----------------------------------------------------------------------------
;  load_monitor: read the system-monitor file described by the boot block
;    boot block +$36 : logical sector of the file's header sector (0 = none)
;    boot block +$38 : load address = entry point; RAM $0..addr-1 is zeroed
;    header  +$40.. : extent list of (start.w, length.w), start = 0 ends it
;  Returns Z = 1 on success.
; -----------------------------------------------------------------------------
800140  342A 0036     load_monitor:
                              move.w  $36(a2),d2
800144  6730                  beq.s   .none
800146  302A 0038             move.w  $38(a2),d0
80014A  E240                  asr.w   #1,d0               ; -> word count to clear
80014C  4EBA 004E             jsr     read_sector(pc)     ; header sector -> buffer
800150  264A                  movea.l a2,a3               ; a3 -> header
800152  4283                  clr.l   d3                  ; block index 0
800154  2443                  movea.l d3,a2               ; a2 = 0
800156  425A          .z:     clr.w   (a2)+               ; zero RAM $0 .. load address
800158  5340                  subq.w  #1,d0
80015A  66FA                  bne.s   .z
80015C  204A                  movea.l a2,a0               ; a0 = a2 = load address = entry
80015E  4EBA 001E     .blk:   jsr     map_block(pc)       ; d3 -> d2 = logical sector (N set past end)
800162  6B0C                  bmi.s   .done
800164  4EBA 0036             jsr     read_sector(pc)     ; 1 KB -> (a2)
800168  D4FC 0400             adda.w  #$400,a2
80016C  5243                  addq.w  #1,d3
80016E  60EE                  bra.s   .blk
800170  4238 FFE6     .done:  clr.b   $FFFFFFE6.w         ; deselect drive
800174  4E75                  rts                         ; Z = 1
800176  4238 FFE6     .none:  clr.b   $FFFFFFE6.w
80017A  7EFF                  moveq   #-1,d7              ; Z = 0
80017C  4E75                  rts

;  map_block: file block d3 -> logical sector d2 via the extent list at a3+$40
80017E  4DEB 0040     map_block:
                              lea     $40(a3),a6
800182  3403                  move.w  d3,d2
800184  4A5E          .e:     tst.w   (a6)+               ; start sector; 0 = end of list
800186  6710                  beq.s   .eof
800188  3E1E                  move.w  (a6)+,d7            ; extent length
80018A  9447                  sub.w   d7,d2
80018C  6AF6                  bpl.s   .e                  ; block lies in a later extent
80018E  D447                  add.w   d7,d2
800190  598E                  subq.l  #4,a6
800192  D456                  add.w   (a6),d2             ; start + offset inside this extent
800194  4287                  clr.l   d7                  ; N = 0
800196  4E75                  rts
800198  7EFF          .eof:   moveq   #-1,d7              ; N = 1
80019A  4E75                  rts

; -----------------------------------------------------------------------------
;  read_sector: logical sector d2 -> 1024 bytes at (a2).  d5 <> 0: double sided
;    track  = d2 / 5, sector-in-track = d2 % 5 + 1
;    double sided: cylinder = track / 2, side = track & 1
;  Prints '.' per sector, 'E' and retries for ever on a read error.
; -----------------------------------------------------------------------------
80019C  48E7 4040     read_sector:
                              movem.l d1/a1,-(sp)
8001A0  123C 002E             move.b  #'.',d1
8001A4  4EBA 01CE     .retry: jsr     putc(pc)
8001A8  11FC 0080 FFE7        move.b  #$80,$FFFFFFE7.w    ; FDC out of reset
8001AE  3C3C 00A1             move.w  #$A1,d6             ; drive/side latch: drive 0, side 0
8001B2  2202                  move.l  d2,d1
8001B4  11C1 FE00             move.b  d1,$FFFFFE00.w      ; display <- sector number being read
8001B8  82FC 0005             divu.w  #5,d1               ; d1.w = track, upper word = sector index
8001BC  4A05                  tst.b   d5
8001BE  6708                  beq.s   .ss
8001C0  E241                  asr.w   #1,d1               ; cylinder = track / 2
8001C2  6404                  bcc.s   .ss
8001C4  0046 0010             ori.w   #$10,d6             ; odd track -> side 1 (latch bit 4)
8001C8  11C6 FFE6     .ss:    move.b  d6,$FFFFFFE6.w
8001CC  4A38 FFE0     .rdy:   tst.b   $FFFFFFE0.w         ; status bit 7 = NOT READY
8001D0  6BFA                  bmi.s   .rdy
8001D2  11C1 FFE3             move.b  d1,$FFFFFFE3.w      ; data register <- cylinder
8001D6  7E08                  moveq   #8,d7
8001D8  5387          .d1:    subq.l  #1,d7
8001DA  66FC                  bne.s   .d1
8001DC  4841                  swap    d1
8001DE  5241                  addq.w  #1,d1               ; sectors are numbered 1..5
8001E0  11C1 FFE2             move.b  d1,$FFFFFFE2.w      ; sector register
8001E4  7E08                  moveq   #8,d7
8001E6  5387          .d2:    subq.l  #1,d7
8001E8  66FC                  bne.s   .d2
8001EA  7E18                  moveq   #$18,d7
8001EC  4EBA 0048             jsr     fdc_command(pc)     ; $18 = SEEK, load head
8001F0  4238 FFE5             clr.b   $FFFFFFE5.w         ; clear INTRQ latch
8001F4  11FC 0080 FFE7        move.b  #$80,$FFFFFFE7.w
8001FA  1E3C 0084             move.b  #$84,d7
8001FE  4EBA 0036             jsr     fdc_command(pc)     ; $84 = READ SECTOR, single, 15 ms settle
800202  4238 FFE5             clr.b   $FFFFFFE5.w
800206  43F8 FFE4             lea     $FFFFFFE4.w,a1      ; sector data port
80020A  3E3C 0400             move.w  #1024,d7
80020E  2C4A                  movea.l a2,a6
800210  1CD1          .rd:    move.b  (a1),(a6)+          ; 1024 bytes; hardware holds the CPU until each is ready
800212  5347                  subq.w  #1,d7
800214  66FA                  bne.s   .rd
800216  1E38 FFE0             move.b  $FFFFFFE0.w,d7      ; FDC status
80021A  0207 001C             andi.b  #$1C,d7             ; RNF | CRC error | lost data
80021E  6710                  beq.s   .ok
800220  11FC 00EE FE00        move.b  #$EE,$FFFFFE00.w    ; display EE: read error
800226  4EBA 0024             jsr     fdc_restore(pc)
80022A  7245                  moveq   #'E',d1
80022C  4EFA FF76             jmp     .retry(pc)
800230  4CDF 0202     .ok:    movem.l (sp)+,d1/a1
800234  4E75                  rts

;  fdc_command: write d7 to the command register and wait for completion
800236  11C7 FFE0     fdc_command:
                              move.b  d7,$FFFFFFE0.w
80023A  0838 0001 FFE6 .w1:   btst    #1,$FFFFFFE6.w      ; wait for INTRQ
800240  67F8                  beq.s   .w1
800242  0838 0000 FFE0 .w2:   btst    #0,$FFFFFFE0.w      ; wait while BUSY
800248  66F8                  bne.s   .w2
80024A  4E75                  rts

;  fdc_restore: pulse the FDC reset line, then RESTORE to track 0
80024C  4238 FFE7     fdc_restore:
                              clr.b   $FFFFFFE7.w
800250  7E40                  moveq   #$40,d7
800252  5387          .d:     subq.l  #1,d7
800254  66FC                  bne.s   .d
800256  11FC 0080 FFE7        move.b  #$80,$FFFFFFE7.w
80025C  7E08                  moveq   #$08,d7
80025E  4EBA FFD6             jsr     fdc_command(pc)     ; $08 = RESTORE, load head
800262  4E75                  rts

; -----------------------------------------------------------------------------
;  Modem download: image arrives on the console port in checksummed blocks
;    4-byte header = end address, then 1 KB blocks from address 0 upward.
;    Block = SOH ($01), data bytes, 8-bit sum.  Reply 'G' = good, 'E' = resend.
; -----------------------------------------------------------------------------
800264  7224          modem_download:
                              moveq   #'$',d1
800266  4EBA 010C             jsr     putc(pc)            ; echo the '$'
80026A  247C 00000000         movea.l #0,a2
800270  7404                  moveq   #4,d2
800272  4EBA 0034             jsr     recv_block(pc)      ; header
800276  2012                  move.l  (a2),d0             ; d0 = end address
800278  243C 00000400         move.l  #1024,d2
80027E  4EBA 0028     .b:     jsr     recv_block(pc)
800282  D5C2                  adda.l  d2,a2
800284  B5C0                  cmpa.l  d0,a2
800286  63F6                  bls.s   .b
800288  2E3C 0007A120         move.l  #500000,d7
80028E  5387          .d:     subq.l  #1,d7
800290  66FC                  bne.s   .d
800292  45FA 0309             lea     msg_esc(pc),a2      ; "Enter ESC to start execution: "
800296  4EBA 00CE             jsr     puts(pc)
80029A  4EBA 00E6     .k:     jsr     getc(pc)
80029E  B23C 001B             cmp.b   #$1B,d1
8002A2  66F6                  bne.s   .k
8002A4  4EFA FE88             jmp     run_loaded(pc)      ; NB: a0 is not set on this path (entry presumably 0)

;  recv_block: d2 bytes -> (a2)
8002A8  48E7 5440     recv_block:
                              movem.l d1/d3/d5/a1,-(sp)
8002AC  4EBA 00D4     .soh:   jsr     getc(pc)
8002B0  B23C 0001             cmp.b   #$01,d1             ; wait for SOH
8002B4  66F6                  bne.s   .soh
8002B6  224A                  movea.l a2,a1
8002B8  3602                  move.w  d2,d3
8002BA  4285                  clr.l   d5
8002BC  4EBA 00C4     .rx:    jsr     getc(pc)
8002C0  12C1                  move.b  d1,(a1)+
8002C2  DA01                  add.b   d1,d5               ; running sum
8002C4  5343                  subq.w  #1,d3
8002C6  66F4                  bne.s   .rx
8002C8  4EBA 00B8             jsr     getc(pc)            ; checksum byte
8002CC  B205                  cmp.b   d5,d1
8002CE  670A                  beq.s   .good
8002D0  7245                  moveq   #'E',d1
8002D2  4EBA 00A0             jsr     putc(pc)
8002D6  4EFA FFD4             jmp     .soh(pc)
8002DA  7247          .good:  moveq   #'G',d1
8002DC  4EBA 0096             jsr     putc(pc)
8002E0  4CDF 022A             movem.l (sp)+,d1/d3/d5/a1
8002E4  4E75                  rts

; -----------------------------------------------------------------------------
;  init_duart: MC68681 at $FFFFFE21 (odd bytes).  A = terminal 9600, B = modem 1200,
;  both 8N1.  Register names per the 68681 data sheet.
; -----------------------------------------------------------------------------
8002E6  11FC 0080 FE29 init_duart:
                              move.b  #$80,ACR            ; baud-rate set 2, counter mode
8002EC  11FC 00BB FE23        move.b  #$BB,CSRA           ; RX/TX clock 9600
8002F2  11FC 0066 FE33        move.b  #$66,CSRB           ; RX/TX clock 1200
8002F8  11FC 0020 FE25        move.b  #$20,CRA            ; reset receiver
8002FE  11FC 0030 FE25        move.b  #$30,CRA            ; reset transmitter
800304  11FC 0040 FE25        move.b  #$40,CRA            ; reset error status
80030A  11FC 0020 FE35        move.b  #$20,CRB
800310  11FC 0030 FE35        move.b  #$30,CRB
800316  11FC 0040 FE35        move.b  #$40,CRB
80031C  11FC 0010 FE25        move.b  #$10,CRA            ; reset MR pointer
800322  11FC 0013 FE21        move.b  #$13,MR1A           ; 8 data bits, no parity, char error mode
800328  11FC 0007 FE21        move.b  #$07,MR2A           ; 1 stop bit, normal mode
80032E  11FC 000A FE25        move.b  #$0A,CRA            ; disable TX and RX
800334  11FC 0010 FE35        move.b  #$10,CRB
80033A  11FC 0013 FE31        move.b  #$13,MR1B
800340  11FC 0007 FE31        move.b  #$07,MR2B
800346  11FC 000A FE35        move.b  #$0A,CRB
80034C  11FC 0004 FE25        move.b  #$04,CRA            ; enable TX
800352  11FC 0004 FE35        move.b  #$04,CRB
800358  11FC 0001 FE25        move.b  #$01,CRA            ; enable RX
80035E  11FC 0001 FE35        move.b  #$01,CRB
800364  4E75                  rts

; -----------------------------------------------------------------------------
;  Console output.  Strings are NUL terminated; bytes >= $80 are screen
;  control codes handled through ctl_table (TeleVideo / ADM-3A sequences).
; -----------------------------------------------------------------------------
800366  4281          puts:   clr.l   d1
800368  121A                  move.b  (a2)+,d1
80036A  6706                  beq.s   .end
80036C  4EBA 0022             jsr     putc_ctl(pc)
800370  60F4                  bra.s   puts
800372  4E75          .end:   rts

800374  1941 0006     putc:   move.b  d1,6(a4)            ; THR
800378  082C 0002 0002 .w:    btst    #2,2(a4)            ; SR: TxRDY
80037E  67F8                  beq.s   .w
800380  4E75                  rts

800382  082C 0000 0002 getc:  btst    #0,2(a4)            ; SR: RxRDY
800388  67F8                  beq.s   getc
80038A  122C 0006             move.b  6(a4),d1            ; RHR
80038E  4E75                  rts

;  putc_ctl: $00-$7F plain; $80-$BF -> table entry (d1 & $3F); $C0-$FF -> entry (d1 & $3F) + 5
800390  4A01          putc_ctl:
                              tst.b   d1
800392  6AE0                  bpl.s   putc
800394  48E7 1010             movem.l d3/a3,-(sp)
800398  0241 007F             andi.w  #$7F,d1
80039C  0881 0006             bclr    #6,d1
8003A0  6702                  beq.s   .i
8003A2  5A41                  addq.w  #5,d1
8003A4  3E01          .i:     move.w  d1,d7
8003A6  E347                  asl.w   #1,d7
8003A8  3E3B 7018             move.w  ctl_table(pc,d7.w),d7
8003AC  4EBB 7014             jsr     ctl_table(pc,d7.w)  ; handler returns a3 -> bytes, d3 = count
8003B0  5303          .o:     subq.b  #1,d3
8003B2  6B08                  bmi.s   .x
8003B4  121B                  move.b  (a3)+,d1
8003B6  4EBA FFBC             jsr     putc(pc)
8003BA  60F4                  bra.s   .o
8003BC  4CDF 0808     .x:     movem.l (sp)+,d3/a3
8003C0  4E75                  rts

;  ctl_table: word offsets relative to $8003C2
8003C2  0010          ctl_table:
                              dc.w    ctl_none-ctl_table  ; 0: $80  (never used; leaves d3 undefined)
8003C4  0026                  dc.w    ctl_gotoxy-ctl_table; 1: $81 row col   cursor address
8003C6  0042                  dc.w    ctl_crlf-ctl_table  ; 2: $82           CR LF
8003C8  FC3E                  dc.w    -$3C2               ; 3: $83  unused (would jump to $800000)
8003CA  FC3E                  dc.w    -$3C2               ; 4: $84  unused
8003CC  FC3E                  dc.w    -$3C2               ; 5: $C0  unused
8003CE  0012                  dc.w    ctl_clreos-ctl_table; 6: $C1           clear to end of screen
8003D0  001C                  dc.w    ctl_clreol-ctl_table; 7: $C2           clear to end of line
8003D2  4E75          ctl_none:
                              rts
8003D4  47FA 0006     ctl_clreos:
                              lea     seq_clreos(pc),a3
8003D8  7602                  moveq   #2,d3
8003DA  4E75                  rts
8003DC  1B 59         seq_clreos:  dc.b $1B,'Y'           ; ESC Y  (bytes appear as 59 1B in word order)
8003DE  47FA 0006     ctl_clreol:
                              lea     seq_clreol(pc),a3
8003E2  7602                  moveq   #2,d3
8003E4  4E75                  rts
8003E6  1B 54         seq_clreol:  dc.b $1B,'T'           ; ESC T
8003E8  1E1A          ctl_gotoxy:
                              move.b  (a2)+,d7            ; row
8003EA  E14F                  lsl.w   #8,d7
8003EC  1E1A                  move.b  (a2)+,d7            ; col
8003EE  47FA 0010             lea     seq_gotoxy(pc),a3
8003F2  0647 2020             addi.w  #$2020,d7           ; + 32 each
8003F6  E05F                  ror.w   #8,d7               ; low byte of the word must land at the lower address
8003F8  3747 0002             move.w  d7,2(a3)            ; patch the template (this is why we run from RAM)
8003FC  7604                  moveq   #4,d3
8003FE  4E75                  rts
800400  1B 3D 00 00   seq_gotoxy:  dc.b $1B,'=',0,0       ; ESC = row+32 col+32
800404  47FA 0006     ctl_crlf:
                              lea     seq_crlf(pc),a3
800408  7602                  moveq   #2,d3
80040A  4E75                  rts
80040C  0D 0A         seq_crlf:    dc.b $0D,$0A

; -----------------------------------------------------------------------------
;  probe_console: set CSR = d4.b on channel a4, ring BEL, wait ~300000 polls
;  for a key.  ESC -> return Z = 1.  Other key -> ring again.  Timeout -> Z = 0.
; -----------------------------------------------------------------------------
80040E  1944 0002     probe_console:
                              move.b  d4,2(a4)            ; CSR
800412  7207                  moveq   #7,d1
800414  4EBA FF5E     .bel:   jsr     putc(pc)
800418  203C 000493E0         move.l  #300000,d0
80041E  082C 0000 0002 .w:    btst    #0,2(a4)            ; RxRDY
800424  6606                  bne.s   .got
800426  5380                  subq.l  #1,d0
800428  6AF4                  bpl.s   .w
80042A  4E75                  rts                         ; timeout, Z = 0
80042C  0C2C 001B 0006 .got:  cmpi.b  #$1B,6(a4)          ; read RHR, is it ESC?
800432  66E4                  bne.s   .bel
800434  4E75                  rts                         ; Z = 1

; -----------------------------------------------------------------------------
;  print_number: d1 = value, d6 = flags (bit 14 octal else decimal, bit 9 to
;  console else to (a2)+, bit 8 space padding, low byte = minimum digits).
;  Not referenced anywhere in the loader; probably shared library code.
; -----------------------------------------------------------------------------
800436  48E7 D840     print_number:
                              movem.l d0-d1/d3-d4/a1,-(sp)
80043A  2006                  move.l  d6,d0
80043C  43FA 0064             lea     tbl_dec(pc),a1
800440  0800 000E             btst    #14,d0
800444  6704                  beq.s   .t
800446  43FA 0086             lea     tbl_oct(pc),a1
80044A  2819          .t:     move.l  (a1)+,d4            ; digit count
80044C  2601                  move.l  d1,d3
80044E  4281          .dig:   clr.l   d1
800450  B691          .sub:   cmp.l   (a1),d3
800452  6506                  bcs.s   .q
800454  5281                  addq.l  #1,d1
800456  9691                  sub.l   (a1),d3
800458  60F6                  bra.s   .sub
80045A  4A81          .q:     tst.l   d1
80045C  6616                  bne.s   .emit
80045E  B8BC 00000001         cmp.l   #1,d4               ; last digit is always printed
800464  670E                  beq.s   .emit
800466  4A00                  tst.b   d0
800468  672C                  beq.s   .next
80046A  0800 0008             btst    #8,d0
80046E  6704                  beq.s   .emit
800470  7220                  moveq   #' ',d1
800472  6010                  bra.s   .store
800474  0681 00000030 .emit:  addi.l  #'0',d1
80047A  0240 FEFF             andi.w  #$FEFF,d0
80047E  4A00                  tst.b   d0
800480  6602                  bne.s   .store
800482  8084                  or.l    d4,d0
800484  B004          .store: cmp.b   d4,d0
800486  650E                  bcs.s   .next
800488  0800 0009             btst    #9,d0
80048C  6706                  beq.s   .buf
80048E  4EBA FEE4             jsr     putc(pc)
800492  6002                  bra.s   .next
800494  14C1          .buf:   move.b  d1,(a2)+
800496  5889          .next:  addq.l  #4,a1
800498  5384                  subq.l  #1,d4
80049A  66B2                  bne.s   .dig
80049C  4CDF 021B             movem.l (sp)+,d0-d1/d3-d4/a1
8004A0  4E75                  rts

; -----------------------------------------------------------------------------
;  Data
; -----------------------------------------------------------------------------
8004A2  tbl_dec:  dc.l 10, 1000000000,100000000,10000000,1000000,100000,10000,1000,100,10,1
8004CE  tbl_oct:  dc.l 11, $40000000,$08000000,$01000000,$00200000,$00040000,$00008000
                  dc.l     $00001000,$00000200,$00000040,$00000008,$00000001

;  Messages (byte order as the CPU reads them; see README "Byte order")
8004FE  msg_banner:  dc.b $1B,'.','0'                     ; TeleVideo 950: cursor off
                     dc.b $81,0,0                         ; cursor home
                     dc.b $C1                             ; clear to end of screen
                     dc.b $81,2,14                        ; row 2, column 14
                     dc.b 'Devtronix Organ Control System Loader Revision C.04',0
80053C  msg_loading: dc.b $81,7,26,'Loading system monitor',$82,$82,0
800558  msg_prompt:  dc.b $81,7,24,'Hit return to boot from disk:'
                     dc.b $81,8,22,'Hit $ to download across modem:',$82,$82,0
80059D  msg_esc:     dc.b $82,$82,'Enter ESC to start execution: ',0
8005BE  msg_nomon:   dc.b $81,15,14,'?No system monitor on this disk',0
8005E1               dc.b 0,0,0,0,0,0,2,0,$41,0,$D7,$18,0,0,0   ; trailer, meaning unknown
8005F0-8007FF        dc.b $FF ...                         ; unprogrammed (end of the 2 KB dump)
