{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem
      (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};

          scripts = import ./scripts.nix { inherit pkgs; };
        in
        {
          devShell = pkgs.mkShell {
            buildInputs = with pkgs; [
              black
              rshell
              ruff

              scripts.firmware.ci
            ];
          };
        }
      );
}
