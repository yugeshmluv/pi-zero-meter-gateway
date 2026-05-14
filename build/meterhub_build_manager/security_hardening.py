"""
Security Hardening Modules for MeterHub

Implements:
- Secure boot configuration
- File integrity monitoring (AIDE)
- Audit logging
- Apparmor profiles
- Kernel hardening
- Network security
"""

import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class SecureBootConfig:
    """Generate secure boot configuration."""

    @staticmethod
    def generate_u_boot_config() -> str:
        """Generate U-Boot secure boot environment."""
        return """
# U-Boot Secure Boot Configuration

# Disable bootloader delay (direct to OS)
bootdelay=0

# Disable UART debug output in production
silent=1

# Require signed images
verify=1

# No interactive console access
interactive=0

# Set bootargs for secure mode
bootargs=ro root=/dev/mmcblk0p2 console=tty1 loglevel=0 quiet vt.handoff=7

# OTA boot variables
mender_boot_part=a
bootcount=0
bootlimit=3
"""

    @staticmethod
    def generate_kernel_cmdline() -> str:
        """Generate hardened kernel command line."""
        return """
# Kernel command line parameters (hardening)

# Disable kernel module loading
module.sig_enforce=1

# Enable SELinux (if available)
security=selinux selinux=1 enforcing=1

# Disable unprivileged namespaces
kernel.unprivileged_userns_clone=0

# Enable ASLR
kernel.randomize_va_space=2

# Restrict access to kernel logs
kernel.dmesg_restrict=1
kernel.sysrq=0

# Restrict kexec
kernel.kexec_load_disabled=1

# Restrict ptrace scope
kernel.yama.ptrace_scope=2

# Restrict access to kernel pointer exposure
kernel.perf_event_paranoid=3

# Disable kprobes (unless needed for debugging)
kernel.kprobes_optimization=0
"""

    @staticmethod
    def generate_sysctl_hardening() -> str:
        """Generate sysctl hardening parameters."""
        return """
# /etc/sysctl.d/99-meterhub-hardening.conf
# Kernel hardening for MeterHub

# ============================================================================
# Kernel Protection
# ============================================================================

# Restrict kernel pointer exposure
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2

# Disable kexec (no kernel switching)
kernel.kexec_load_disabled = 1

# Restrict ptrace scope (prevent debugging)
kernel.yama.ptrace_scope = 2

# Restrict perf events (prevent side-channel attacks)
kernel.perf_event_paranoid = 3

# Enable SMEP (Supervisor Mode Execution Prevention)
kernel.smap_alignment_check = 1

# Restrict access to sysrq
kernel.sysrq = 0

# ============================================================================
# Memory Protection
# ============================================================================

# Enable ASLR (Address Space Layout Randomization)
kernel.randomize_va_space = 2

# Restrict unprivileged namespace creation
kernel.unprivileged_userns_clone = 0
kernel.unprivileged_bpf_disabled = 1
kernel.unprivileged_bpf_disabled_default = 1

# Restrict access to unprivileged ebpf
kernel.bpf_stats_enabled = 0

# ============================================================================
# Network Security
# ============================================================================

# Disable IP forwarding
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Disable ICMP redirects (prevent MITM)
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0

# Enable SYN cookies (SYN flood protection)
net.ipv4.tcp_syncookies = 1

# Log suspicious packets
net.ipv4.conf.all.log_martians = 1

# Disable source packet routing
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Restrict ICMP ping
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Enable bad error message protection
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Increase TCP backlog
net.ipv4.tcp_max_syn_backlog = 2048
net.core.netdev_max_backlog = 5000

# ============================================================================
# File System Security
# ============================================================================

# Restrict access to kernel logs
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.protected_regular = 2
fs.protected_fifos = 2

# Restrict core dumps
fs.suid_dumpable = 0
kernel.core_uses_pid = 1

# Inotify limits (prevent DoS)
fs.inotify.max_user_watches = 8192
fs.inotify.max_user_instances = 128
"""


class AideConfig:
    """Generate AIDE (File Integrity Monitor) configuration."""

    @staticmethod
    def generate_aide_rules() -> str:
        """Generate AIDE rules for critical files."""
        return """
# /etc/aide/aide.conf.d/meterhub
# AIDE configuration for MeterHub device

# ============================================================================
# Global Rules
# ============================================================================

# Define custom rules
$MeterHub = p+i+u+g+b+m+c+md5+sha256

# ============================================================================
# Critical System Files
# ============================================================================

# U-Boot bootloader
/boot/bootloader = $MeterHub
/boot/uboot_env = $MeterHub

# Device tree
/boot/*.dtb = $MeterHub

# Kernel and modules
/boot/vmlinuz* = $MeterHub
/lib/modules = $MeterHub

# ============================================================================
# System Configuration
# ============================================================================

# SSH configuration
/etc/ssh = $MeterHub

# System users and groups
/etc/passwd = $MeterHub
/etc/group = $MeterHub
/etc/shadow = $MeterHub

# Network configuration
/etc/network = $MeterHub
/etc/hostname = $MeterHub

# MeterHub configuration
/etc/meterhub = $MeterHub

# ============================================================================
# MeterHub Service Files
# ============================================================================

/opt/meterhub = $MeterHub
/var/lib/meterhub = L+b+sha256

# ============================================================================
# Exclusions (frequently changing files)
# ============================================================================

!/var/log
!/var/cache/meterhub/telemetry
!/var/cache/meterhub/updates
!/var/lib/systemd/journal
"""


class ApparmorProfile:
    """Generate Apparmor security profiles."""

    @staticmethod
    def generate_acquisition_profile() -> str:
        """Generate Apparmor profile for acquisition service."""
        return """#include <tunables/global>

# MeterHub Acquisition Service Apparmor Profile
/opt/meterhub/bin/acquisition {
  #include <abstractions/base>
  #include <abstractions/python>
  #include <abstractions/nameservice>

  # Allow reading system files
  /sys/class/gpio/ r,
  /sys/devices/platform/soc/ r,
  /sys/bus/i2c/ r,

  # Serial port access (Modbus)
  /dev/ttyUSB* rw,
  /dev/ttyAMA* rw,

  # Allow RTC access
  /dev/i2c-* rw,

  # Database access
  /var/cache/meterhub/telemetry.db rw,
  /var/lib/meterhub/state.db rw,

  # Configuration files (read-only)
  /etc/meterhub/*.yaml r,
  /etc/meterhub/device_config.json r,

  # Logs
  /var/log/meterhub/ w,
  /var/log/meterhub/*.log w,

  # Libraries
  /usr/lib/python3.11/** r,
  /opt/meterhub/venv/lib/** r,

  # Deny everything else
  deny /etc/shadow rwx,
  deny /etc/gshadow rwx,
  deny /root/** rwx,
}
"""

    @staticmethod
    def generate_uploader_profile() -> str:
        """Generate Apparmor profile for uploader service."""
        return """#include <tunables/global>

# MeterHub Uploader Service Apparmor Profile
/opt/meterhub/bin/uploader {
  #include <abstractions/base>
  #include <abstractions/python>
  #include <abstractions/nameservice>

  # Network access required
  #include <abstractions/openssl>
  #include <abstractions/ssl_certs>
  /etc/ssl/certs/** r,

  # Database (telemetry read, state write)
  /var/cache/meterhub/telemetry.db r,
  /var/lib/meterhub/state.db rw,

  # Configuration files
  /etc/meterhub/*.json r,

  # Certificates for MQTT/HTTPS
  /etc/meterhub/certs/** r,

  # Logs
  /var/log/meterhub/ w,
  /var/log/meterhub/*.log w,

  # Network access (socket)
  network inet stream,
  network inet dgram,
  network inet6 stream,
  network inet6 dgram,

  # Libraries
  /usr/lib/python3.11/** r,
  /opt/meterhub/venv/lib/** r,

  # Deny dangerous operations
  deny /etc/shadow rwx,
  deny /root/** rwx,
  deny /opt/meterhub/venv/bin/python rwx,
}
"""

    @staticmethod
    def generate_installer_profile() -> str:
        """Generate Apparmor profile for installer UI service."""
        return """#include <tunables/global>

# MeterHub Installer UI Apparmor Profile
/opt/meterhub/bin/installer-ui {
  #include <abstractions/base>
  #include <abstractions/python>
  #include <abstractions/nameservice>

  # Network access (HTTPS)
  #include <abstractions/openssl>
  #include <abstractions/ssl_certs>

  # System access (for network scanning)
  /sys/class/net/ r,
  /sys/devices/virtual/net/ r,

  # Device files
  /dev/null rw,
  /dev/zero rw,
  /dev/urandom r,

  # Configuration
  /etc/meterhub/device_config.json rw,
  /etc/meterhub/certs/** r,

  # Logs
  /var/log/meterhub/ w,
  /var/log/meterhub/*.log w,

  # Network tools (nmcli)
  /usr/bin/nmcli ix,
  /usr/bin/wpa_cli ix,

  # Meter profile access
  /etc/meterhub/profiles/*.yaml r,

  # Database access
  /var/cache/meterhub/telemetry.db r,

  # Libraries
  /usr/lib/python3.11/** r,
  /opt/meterhub/venv/lib/** r,
}
"""


class FirewallConfig:
    """Generate firewall rules."""

    @staticmethod
    def generate_ufw_rules() -> str:
        """Generate UFW firewall rules."""
        return """
#!/bin/bash
# UFW firewall configuration for MeterHub

# Set default policies
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

# Allow essential services
ufw allow 22/tcp comment "SSH (installer access)"
ufw allow 8443/tcp comment "Installer UI (HTTPS)"

# Allow only from local network (if configured)
# ufw allow from 192.168.1.0/24 to any port 22 proto tcp
# ufw allow from 192.168.1.0/24 to any port 8443 proto tcp

# Block commonly scanned ports
ufw deny 23/tcp comment "Deny Telnet"
ufw deny 445/tcp comment "Deny SMB"
ufw deny 3389/tcp comment "Deny RDP"

# Enable firewall
ufw --force enable

# Show rules
ufw status verbose
"""


class KernelHardening:
    """Kernel hardening utilities."""

    @staticmethod
    def get_build_flags() -> dict[str, str]:
        """Get recommended kernel build flags for hardening."""
        return {
            "CONFIG_HAVE_EFFICIENT_UNALIGNED_ACCESS": "n",  # Enable alignment checks
            "CONFIG_DEBUG_CREDENTIALS": "y",
            "CONFIG_DEBUG_NOTIFIERS": "y",
            "CONFIG_DEBUG_BUGVERBOSE": "y",
            "CONFIG_PAGE_POISONING": "y",
            "CONFIG_PAGE_POISONING_ZERO": "y",
            "CONFIG_CC_STACKPROTECTOR": "y",
            "CONFIG_CC_STACKPROTECTOR_STRONG": "y",
            "CONFIG_STRICT_KERNEL_RWX": "y",
            "CONFIG_STRICT_MODULE_RWX": "y",
            "CONFIG_DEBUG_RODATA": "y",
            "CONFIG_DEBUG_SET_MODULE_RONX": "y",
            "CONFIG_RETPOLINE": "y",
            "CONFIG_RETPOLINE_CRYPTO": "y",
            "CONFIG_SYN_COOKIES": "y",
            "CONFIG_DEFAULT_MMAP_MIN_ADDR": "32768",
            "CONFIG_SECCOMP": "y",
            "CONFIG_SECCOMP_FILTER": "y",
            "CONFIG_SECURITY": "y",
            "CONFIG_SECURITY_APPARMOR": "y",
            "CONFIG_SECURITY_APPARMOR_HASH": "y",
            "CONFIG_AUDIT": "y",
            "CONFIG_AUDIT_WATCH": "y",
            "CONFIG_AUDIT_TREE": "y",
        }

    @staticmethod
    def get_module_blacklist() -> list[str]:
        """Get list of kernel modules to blacklist."""
        return [
            "cramfs",  # Unused filesystem
            "freevxfs",  # Unused filesystem
            "jffs2",  # Unused filesystem
            "hfs",  # Mac filesystem
            "hfsplus",  # Mac filesystem
            "udf",  # UDFS filesystem
            "cifs",  # SMB filesystem
            "nfs",  # NFS filesystem
            "usb_storage",  # USB storage (disable if not needed)
            "firewire",  # FireWire (unused)
            "bluetooth",  # Bluetooth (if not needed)
        ]
