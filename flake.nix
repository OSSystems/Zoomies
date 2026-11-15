{
  description = "Zoomies - a playful NixOS desktop for kids, packed with open-source games";

  inputs = {
    # Not following our nixpkgs keeps its Raspberry Pi kernels hitting its
    # binary cache.
    nixos-raspberrypi.url = "github:nvmd/nixos-raspberrypi/main";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    pedantix = {
      inputs.nixpkgs.follows = "nixpkgs";
      url = "github:Swarsel/pedantix";
    };
    red-tape = {
      inputs.nixpkgs.follows = "nixpkgs";
      url = "github:phaer/red-tape";
    };
    treefmt-nix = {
      inputs.nixpkgs.follows = "nixpkgs";
      url = "github:numtide/treefmt-nix";
    };
  };

  # Prebuilt Raspberry Pi kernels; building one under emulation takes hours.
  nixConfig = {
    extra-substituters = [ "https://nixos-raspberrypi.cachix.org" ];
    extra-trusted-public-keys = [
      "nixos-raspberrypi.cachix.org-1:4iMO9LXa8BqhU+Rpg6LQKiGa2lsNh/j2oiYLNOQ5sPI="
    ];
  };

  outputs =
    { self, ... }@inputs:
    inputs.red-tape.mkFlake {
      inherit inputs self;
      prefix = "nix";
      src = ./.;
      systems = [
        "aarch64-linux"
        "x86_64-linux"
      ];
    };
}
