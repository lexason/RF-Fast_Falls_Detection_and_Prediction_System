# N210 FPGA Compat-11 Build Guide

**RESOLVED 2026-07-18.** `uhd_usrp_probe` now succeeds completely (FPGA
11.1, FW 12.4, daughterboard UBX-40 v2) after: building a from-source
bitstream (this guide), resolving a WebPACK device-tier exclusion and a
FlexLM hostid-detection bug along the way, flashing it, and finally a
physical power cycle of the device -- see `STATE.md`'s 2026-07-18 "G0
CLOSED" entry for the full closing evidence. This doc is kept as the
complete diagnostic and build record, useful if the FPGA ever needs
rebuilding again (e.g. after a UHD upgrade bumps the compat number further).

**Original status (2026-07-17):** G0 hardware verification is blocked. `uhd_usrp_probe`
fails with "Expected FPGA compatibility number 11, but got 10." Root cause and
alternatives are logged in `STATE.md`. This doc is the step-by-step for the
chosen long-term fix: building a matching FPGA bitstream from source. See
`STATE.md`'s session ledger for the full diagnostic trail (3 reflash attempts,
2 UHD versions, ruled out timing/reboot as the cause).

**Confirmed feasibility:** the compat number is hardcoded in the RTL at
`~/src/uhd/fpga/usrp2/top/N2x0/u2plus_core.v:451`:
`localparam compat_num = {16'd11, 16'd1};` — major 11, matching what this
host's UHD (tag `v4.9.0.0`) expects. The publicly published prebuilt image
(`fpga-6bea23d`) does not match this source tree for the N210 target and
reports compat 10 instead. Building from this exact checked-out tree should
produce a bitstream that resolves the mismatch.

---

## Phase 1 — Account and toolchain acquisition (researcher only)

1. **Create a free AMD/Xilinx account** if you don't have one. Claude cannot
   do this — it requires personal registration and credentials.
2. **Download ISE Design Suite 14.7** from
   `https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/legacy-ise/v2012_4---14_7.html`.
   Our target FPGA is a **Spartan-3A DSP (`xc3sd3400a`)** (confirmed from
   `Makefile.N210R4`).
   - **Vivado will not work.** AMD dropped Spartan-3 support entirely; ISE
     14.7 (2013) is the last release that supports this device family.
   - **Pick "Full Installer for Linux"** — AMD's actual filename was
     `Xilinx_ISE_DS_Lin_14.7_1015_1.tar` (a plain `.tar`, not `.tar.gz`),
     6.5 GB. Not the Windows installer, not the "Full DVD" combined image.
   - **Resolved 2026-07-17 — WebPACK does NOT include `xc3sd3400a`:**
     confirmed empirically, not from documentation (which was ambiguous/
     wrong — some third-party sources claim WebPACK covers it; it doesn't
     on this actual install). `partgen -arch spartan3adsp` under a WebPACK
     install only lists `xc3sd1800a`. This matches a consistent pattern
     across every Spartan-3 sub-family checked (plain Spartan-3, Spartan-3A,
     Spartan-3A DSP): WebPACK bundles every device in each family **except
     the single largest/top-tier part**, which is exactly the part the N210
     uses. **ISE Design Suite Logic Edition does include it** — confirmed
     via `partgen` showing `xc3sd3400a` present after a Logic Edition
     install, still with zero license file configured. So this is a
     device-data bundling difference between editions, not a runtime
     license-key requirement — see Phase 2 for exactly how this was
     installed and verified.
3. Expect a multi-GB download, and note the download itself requires being
   logged into your AMD/Xilinx account (Claude cannot do this step).

## Phase 2 — Transfer and installation

**Transfer (researcher):** downloading on a Windows machine and moving the
file to this Ubuntu box over SSH. Copy the tarball to `~/Downloads/` (already
exists) — from PowerShell with OpenSSH's `scp` client (Windows 10+ ships
this by default), or WinSCP if you prefer a GUI:
```powershell
scp .\ISE_DS_Lin_full_2013_10_23.tar.gz sdr-research@<ubuntu-host>:~/Downloads/
```
(adjust the filename to whatever AMD actually names the download). Once it's
landed in `~/Downloads/`, tell Claude — it can take over from there.

**Installation — what actually happened, 2026-07-17 (no sudo needed at all):**
4. Extracted to `~/Xilinx/installers/Xilinx_ISE_DS_Lin_14.7_1015_1/` (from
   `~/Downloads/Xilinx_ISE_DS_Lin_14.7_1015_1.tar` — note: AMD's actual
   download was a plain `.tar`, not `.tar.gz` as assumed earlier).
5. **Missing `libncurses.so.5`:** running `xsetup` failed immediately —
   Ubuntu 24.04 dropped this legacy ABI from its repos entirely (confirmed:
   `apt-cache policy libncurses5` returns nothing). Fixed **without sudo**
   by downloading the plain (non-dev) runtime `.deb` packages from Ubuntu's
   permanent EOL archive and extracting just the `.so` files with
   `dpkg-deb -x` into `~/Xilinx/compat-libs/lib/`, then setting
   `LD_LIBRARY_PATH` to include that dir for the installer run only:
   - `http://old-releases.ubuntu.com/ubuntu/pool/main/n/ncurses/libncurses5_6.1+20190803-1ubuntu1_amd64.deb`
   - `http://old-releases.ubuntu.com/ubuntu/pool/main/n/ncurses/libtinfo5_6.1+20190803-1ubuntu1_amd64.deb`
   - (`launchpadlibrarian.net`, the other common source for these, was
     unreachable from this network — TCP connected but the HTTP response
     never came, on both port 80 and 443. `old-releases.ubuntu.com` worked
     fine.)
6. **Batch/silent install:** `xsetup --help` only shows `--uninstall`,
   `--copy_registry`, `--noencrypt` — no batch flag. The real mechanism is a
   **separate binary**, `bin/lin64/batchxsetup`:
   ```bash
   ./bin/lin64/batchxsetup --samplebatchscript <path>   # generates a template
   ./bin/lin64/batchxsetup --batch <path>                # runs it
   ```
   Template controls: `destination_dir=`, `copy_preferences=`,
   `use_multiple_cores=`, and per-edition blocks toggled by
   commenting/uncommenting and a trailing `::1` (selected) / `::0` (not) on
   the `package=` line. First attempt selected **ISE WebPACK** — see the
   `xc3sd3400a` finding in Phase 1: WebPACK installed fine but doesn't
   include this device, so a second install with **ISE Design Suite Logic
   Edition** selected instead was needed (same mechanics, different
   `package=` block uncommented). Both runs left
   `application=Acquire or Manage a License Key::0` and
   `application=Install Cable Drivers::0` unselected — no USB/JTAG cable is
   used in this workflow (the N210 build/flash path is all over Ethernet),
   and neither install has needed a license file so far (see Phase 4).
   **The installer refuses to reinstall into an already-populated
   `destination_dir`** ("Setup has detected existing Xilinx software
   installation... select a new destination directory") — it's not an
   incremental/add-on installer, so the Logic Edition run used a separate
   directory rather than overwriting the WebPACK one.
7. **Two more installer quirks hit and fixed:**
   - `TERM environment variable not set` — exited instantly even though
     `$TERM` was actually `dumb`, not unset; the installer's own check
     apparently doesn't accept that value. Fixed with `TERM=xterm`.
   - With `TERM` fixed, the installer then paginates the full EULA text via
     an ncurses pager and demands a literal `Y` keypress to accept
     (`I accept and agree... Enter "Y" to accept or "N" to reject:`) — with
     no interactive terminal attached, it re-prompted in a tight loop and
     generated **multiple gigabytes of repeated output in under a minute**
     before being killed. Fixed by piping `yes Y` into its stdin:
     ```bash
     yes Y | env TERM=xterm LD_LIBRARY_PATH=~/Xilinx/compat-libs/lib:$LD_LIBRARY_PATH \
         ./bin/lin64/batchxsetup --batch ~/Xilinx/installers/batch-config/ise_batch.txt
     ```
     **If you ever rerun this installer, watch the output/log size in real
     time** rather than leaving it fully unattended — this failure mode
     produces runaway disk usage fast (we hit ~9 GB of log across two
     stuck attempts before catching it).
   - Installer also silently nests its own version directory under whatever
     `destination_dir` you give it — see Phase 3 below for the resulting
     real path.
8. Each full install (WebPACK, then Logic Edition): **18 GB**, completed
   cleanly in well under a minute of actual product-copy time
   (`Installation is complete.`) once the EULA prompt was handled — the
   friction was entirely the quirks above, not the raw install itself.
   Two installs exist on disk: `~/Xilinx/14.7/` (WebPACK — missing
   `xc3sd3400a`, kept for reference/smaller footprint if ever needed for
   other parts) and `~/Xilinx/14.7-logic-test/` (Logic Edition — has
   `xc3sd3400a`, this is the one Phase 3/4 actually use).
9. **License activation turned out not to matter (so far).** Neither
   install has an active license file, yet Logic Edition's `partgen` shows
   `xc3sd3400a` and project setup accepts it — so the WebPACK/Logic split
   is a device-database packaging difference, not a runtime license
   check, at least through project creation. Whether `bitgen` (final
   bitstream generation) enforces a license at the very end is still
   unknown until Phase 4 completes — if it does, generate one via AMD's
   licensing portal and hand Claude the resulting `.lic` file path to set
   `XILINXD_LICENSE_FILE`.

## Phase 3 — Environment setup (done 2026-07-17)

10. Source the **Logic Edition** environment before building (not the
    WebPACK one — it lacks `xc3sd3400a`):
    ```bash
    source ~/Xilinx/14.7-logic-test/14.7/ISE_DS/settings64.sh
    ```
    Note the doubled `14.7/14.7` in the real path under each install
    root — the batch installer appends its own version-numbered
    subdirectory under whatever `destination_dir` is given.
    Confirmed: `xtclsh -h` resolves and reports `Release 14.7 - xtclsh
    P.20131013 (lin64)` — the build system detects the ISE version this way
    (`~/src/uhd/fpga/usrp2/top/Makefile.common:8`), and it works standalone
    (ISE's own `settings64.sh` sets up its own library paths; the
    `libncurses.so.5` workaround from Phase 2 was only needed for the
    installer itself, not for running the toolchain afterward).
11. **One more quirk:** `partgen -arch spartan3adsp` confirms the device,
    but the very first `make N210R4` attempt failed differently —
    `make[1]: python: Permission denied`. Root cause: `/usr/local/lib/uhd/
    examples/python` is a **directory** (UHD's bundled example scripts,
    not an executable), and it sits earlier in `$PATH` than any real
    `python`/`python3` binary — so the shell tried to exec a directory and
    got `EACCES` instead of finding an interpreter. This system also has no
    plain `python` at all, only `python3` (Ubuntu 24.04 default). Fixed
    with a personal symlink, since `~/bin` is already early in `$PATH`:
    ```bash
    ln -sf /usr/bin/python3 ~/bin/python
    ```

## Phase 4 — Build (Claude can drive this once Phase 1–3 are done)

12. From `~/src/uhd/fpga/usrp2/top/N2x0/`, run:
    ```bash
    make N210R4
    ```
    This expands to `make -f Makefile.N210R4 bin`, which runs XST synthesis →
    `ngdbuild` → `map` → `par` → `bitgen` via `xtclsh` and Ettus's
    `tcl/ise_helper.tcl`, then a Python timing-margin check
    (`check_timing.py`) that **fails the build if timing isn't met**.
    Spartan-3A DSP designs sometimes need constraint tweaks or a rerun to
    close timing — this is a real risk of iteration, not guaranteed one-shot.
13. Output lands at `build14-N210R4/u2plus.bin` (the `14` prefix depends on
    the ISE major version `xtclsh` reports).
14. **Result, 2026-07-17: got through XST synthesis cleanly (0 errors),
    failed at `map` on a genuine FLEXnet license error — blocked here,
    not a Claude-side problem to solve further.**
    ```
    ERROR:Security:12 - No 'xc3sd3400a' feature version 2013.10 was available (-5),
        so 'WebPack' may not be used.
    ERROR:Map:258 - A problem was encountered attempting to get the license for this
        architecture.
    ```
    Context: both batch installs deliberately left
    `application=Acquire or Manage a License Key::0` unselected (Phase 2),
    since license acquisition needs the researcher's AMD account and can't
    be scripted by Claude. Synthesis (`xst`) apparently doesn't check
    licenses; `map` (place-and-map) does, per-device.

    **Resolved 2026-07-17 — this device is definitively not a free-tier
    part, confirmed by Xilinx's own tooling, not just absence from a device
    list.** Researcher generated and installed a WebPACK license
    (`ISE_WebPACK` feature, `HOSTID=ANY`, permanent) via AMD's portal
    ("Create New Licenses" → "ISE Design Suite: WebPACK License" →
    "Generate Node-Locked License"). Installed to `~/.Xilinx/Xilinx.lic`
    and via `XILINXD_LICENSE_FILE`. Rebuilt from scratch — the license file
    was found and read correctly (`License path:` in the log lists it), but
    `map` failed with the *same* error, this time with an explicit reason:
    ```
    INFO:Security:56 - Part 'xc3sd3400a' is not a WebPack part.
    ...
    ERROR:Security:12 - No 'xc3sd3400a' feature version 2013.10 was available (-5),
        so 'WebPack' may not be used.
    ```
    This is Xilinx's own security-check tooling stating outright that
    `xc3sd3400a` isn't in the WebPACK product line — not a missing license,
    not a missing device file, a real product-tier exclusion. No WebPACK
    license, however generated, will ever cover this part. This matches
    (and now fully explains) the earlier `partgen -arch spartan3adsp`
    finding that WebPACK's installed device database omits it.
    - **Remaining real options:** (a) a paid Logic Edition (or higher)
      license covering this part — cost unknown, needs the researcher to
      check AMD's store/pricing; (b) AMD's portal has an "Evaluation and
      No Charge Cores" search (visible in the same license-creation UI) —
      worth checking whether a time-limited full-featured eval license
      covers Spartan-3A DSP, since that would be free; (c) abandon this
      build path and return to the physical-power-cycle option for the
      N210 (still untested all session — see `STATE.md`).
    - Not pursued further without checking in first, since this now
      depends entirely on what's actually available/affordable through
      the researcher's account — not something to guess into via more
      trial-and-error installs.
16. **Second license tested (2026-07-17): `ISE Embedded Edition License`**
    (also no-charge, a different product tier from WebPACK — visible on
    AMD's licensing portal as `Certificate - No Charge`). Its `COMPONENTS`
    list explicitly includes `ISE` (unlike the WebPACK license, whose
    components were Zynq-specific), so this looked like a genuine base-tool
    license rather than a device add-on. Generated host-locked to
    `d4a2cda44fc3` (the MAC of `enp128s31f6`, this machine's active
    interface) per the portal's "Ethernet Address" host ID type.

    Result: different failure — **`Invalid host`**, not a device-eligibility
    error this time:
    ```
    INFO:Security:7 - A feature for ISE was found but is for the wrong hostid.
    Invalid host.
     The hostid of this system does not match the hostid specified in the license file.
    Feature:       ISE
    Hostid:        d4a2cda44fc3
    ```
    Root cause, confirmed directly: this ISE install's bundled `lmutil`
    binary can't run via its own hardcoded ELF interpreter path
    (`/lib64/ld-lsb-x86-64.so.3`, an old LSB compat symlink Ubuntu 24.04
    doesn't ship) — worked around with
    `/lib64/ld-linux-x86-64.so.2 <path-to-lmutil> lmhostid -ether`, which
    invokes the real dynamic linker directly, no sudo/system changes
    needed. **FlexLM's actual Ethernet-Address detection on this machine
    reports `000000000000`** — a degenerate all-zero fallback, not the real
    MAC of any interface (checked `-ether`, `-string`: both agree; this
    2012-era FlexLM binary apparently can't read this modern NIC correctly,
    likely an interface-naming or driver incompatibility). This has nothing
    to do with which edition/product is licensed — it's a host
    identification bug that would affect *any* node-locked license
    generated with a real MAC address on this machine.

    **Fix, attempt 1:** regenerating with Host ID Value `000000000000`
    doesn't work — AMD's portal client-side validation rejects an
    all-zero MAC as invalid before the license can even be created.
17. **Real fix:** rather than fighting the portal's validation with a
    degenerate value, fixed the actual detection gap. `strace -e
    network,ioctl` on `lmutil lmhostid -ether` showed exactly what it
    probes:
    ```
    ioctl(3, SIOCGIFHWADDR, {ifr_name="xp0"})   = -1 ENODEV
    ioctl(3, SIOCGIFHWADDR, {ifr_name="eth0"})  = -1 ENODEV
    ... eth1-eth9, bond0-9, vmnic0-9 ...        = -1 ENODEV
    ```
    This 2012-era binary only checks a hardcoded list of legacy interface
    names — it never tries `enp128s31f6` (predictable network interface
    naming postdates this tool), hence the all-zero fallback. Fixed by
    creating an additional interface literally named `eth0` (a macvlan
    bound to the real NIC, not a rename — `enp128s31f6` stays completely
    untouched, this is purely additive):
    ```bash
    sudo ip link add eth0 link enp128s31f6 address 02:00:00:00:00:01 type macvlan mode bridge
    sudo ip link set eth0 up
    ```
    `lmutil lmhostid -ether` then correctly reports `020000000001`.
    Regenerated the Embedded Edition license with that value as Host ID —
    portal validation passed, and a rebuild got **past `map` with zero
    license errors** for the first time all session: real timing-driven
    placement work running (clock region assignment, global placement
    phases), not a security-check failure. This confirms both the hostid
    fix and that `ISE Embedded Edition` (unlike WebPACK) does cover
    `xc3sd3400a` for implementation.
    - **Persistence note:** the `eth0` macvlan interface needs to exist
      and be up any time the ISE tools run (`map`/`par`/`bitgen` all
      re-check the license), not just once. It won't survive a reboot
      unless made persistent — revisit if this session's interface
      disappears after a restart.
18. **Build succeeded completely.** `par` (place & route) finished with 0
    timing warnings; `bitgen` completed ("Process 'Generate Programming
    File' completed successfully"). Output: `build-N210R4/u2plus.bin`,
    1,464,788 bytes — confirmed genuinely different from the historically
    broken prebuilt image (different checksum, different size: 1,464,788
    vs. 1,299,084 bytes) and structurally valid (correct Xilinx bitstream
    sync word `aa99 30a1` and preamble format, checked via `xxd`).

## Phase 5 — Flash and verify: done, one step short of resolving G0

Flashed twice (once `--fpga-path` only, once with firmware included too, to
rule out `--no-fw` skipping some reboot trigger) — both report
"successful" with verify passing. **`uhd_usrp_probe` still reports compat
10, not 11, after both flashes and multiple wait times (10–15s).**

This is very likely the same untested variable flagged at the very start
of this whole diagnostic chain (`STATE.md`'s first session entry): the
SPI configuration flash content is now genuinely correct and verified, but
nothing triggers the FPGA fabric to actually reload its configuration from
that flash over the network — on USRP2/N-series hardware this appears to
require a true power-on reset, and no software/network reboot mechanism
exists for this device family (confirmed earlier: no reboot opcode in the
USRP2 protocol, `usrpctl reset` is MPM-only for newer embedded-Linux
USRPs). Not a build problem, not a flash problem — both are now confirmed
correct and complete.

**Next step: a physical power cycle of the N210** (unplug/replug), the one
variable never tested all session since the researcher has had remote-only
SSH access throughout.
15. **Time budget, revised now that Phases 1–4 have actually been run:** the
    account/download/transfer took about as long as the file transfer
    itself; each install (Phase 2) was under a minute of actual copy time —
    the real cost was working out the `libncurses5`/`TERM`/EULA/
    device-edition/`python` quirks above, not the raw install. Project setup
    and XST synthesis together took a few minutes once those were fixed.
    The remaining unknown is entirely the license step (Researcher) plus
    whatever `map`/`par`/`bitgen` actually take once licensed — untested.

---

## Division of labor

| Step | Who | Status |
|---|---|---|
| Create AMD/Xilinx account, download the installer | Researcher | done |
| Transfer installer to `~/Downloads/` on this machine | Researcher (scp) | done |
| Extract, resolve `libncurses.so.5`, run batch install (WebPACK, then Logic Edition) | Claude | done — **no sudo needed at all**, contrary to the original guess (Phase 2) |
| Discover `xc3sd3400a` needs Logic Edition, not WebPACK; fix `python` PATH shadowing | Claude | done (Phase 1/3) |
| Source the environment, confirm `xtclsh` | Claude | done |
| Generate a WebPACK license, install it, retry the build | Researcher generated it; Claude installed + retried | done — **confirmed `xc3sd3400a` is not a WebPack part at all**, per Xilinx's own tooling. WebPACK is a dead end for this device. |
| Generate `ISE Embedded Edition` license (no-charge, different tier), diagnose+fix hostid detection bug, retry | Researcher generated it (twice — once wrong hostid, then corrected); Claude diagnosed the hostid bug (`strace`), fixed it (macvlan `eth0` interface, no sudo needed beyond one `ip link add`), installed the corrected license | done — **`map`/`par`/`bitgen` all succeeded, zero license errors.** Working bitstream produced. |
| Flash (`uhd_image_loader`) and verify (`uhd_usrp_probe`) | Claude | done — flash succeeds and verifies cleanly (twice), but **probe still reports compat 10, not 11** |
| Physical power cycle of the N210 | **Researcher — this is the actual, final next step** | **blocking** — everything software-side is confirmed correct; this looks like the same untested variable flagged at the very start of the whole diagnostic chain |

## Why this is expected to fix it, not just another guess

Unlike the earlier reflash attempts (which used the pre-built binary pinned
in `manifest.txt` — confirmed byte-identical whether from the local cache or
freshly downloaded from files.ettus.com), this path compiles directly from
the RTL source already checked out at the same tag (`v4.9.0.0`) this
machine's UHD was built from. The compat constant in that source is `11`,
matching host expectations exactly — the mismatch appears to be a packaging
bug in what Ettus published as the prebuilt N210 default image, not a defect
in the source tree itself.

## What NOT to do

Do not patch `N200_FPGA_COMPAT_NUM` down to 10 in host code to force-accept
the mismatched prebuilt image instead of doing this build. That bypasses a
real protocol/register-map compatibility guard; if the actual DDC/decimation
behavior or register layout differs between what the host expects and what
that image implements, it could silently produce corrupted sample timing or
VITA framing — bad data that doesn't necessarily crash. See `STATE.md`'s
2026-07-17 entries for the full reasoning.
