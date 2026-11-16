# The last console= becomes /dev/console, so boot messages stay on the
# screen; the serial console helps debug machines and VMs.
{
  boot.kernelParams = [
    "console=ttyS0,115200n8"
    "console=tty0"
  ];
}
