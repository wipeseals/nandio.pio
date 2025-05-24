{
    description = "A flake for a Python and MicroPython development environment";

    inputs = {
        nixpkgs.url = "github:NixOS/nixpkgs";
    };

    outputs = { self, nixpkgs }:
    let
        pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in
     {
        devShell.x86_64-linux = pkgs.mkShellNoCC {
            packages = with pkgs; [
                python312
                python312.pkgs.uv
                python312.pkgs.pytest   
                python312.pkgs.jupyter   
                micropython             
                gtkwave
            ];
        };
    };
}