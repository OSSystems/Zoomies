{
  description = "Zoomies - a playful NixOS desktop for kids, packed with open-source games";

  inputs = {
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

  outputs =
    { self, ... }@inputs:
    inputs.red-tape.mkFlake {
      inherit inputs self;
      prefix = "nix";
      src = ./.;
      systems = [ "x86_64-linux" ];
    };
}
