{
  description = "AlgoBot reproducible Tembo development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          python312
          python312Packages.pip
          python312Packages.virtualenv
          git
          gcc
          pkg-config
          openssl
          libffi
          postgresql
          redis
        ];

        shellHook = ''
          export PYTHONUNBUFFERED=1
          export PIP_DISABLE_PIP_VERSION_CHECK=1
        '';
      };
    };
}
