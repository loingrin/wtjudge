"""Recreate only bundled demo paths, never user submissions."""
from pathlib import Path


def make_demo(root):
    root = Path(root)
    for name, count in [("apple", 3), ("road", 6), ("tree", 10), ("game", 25)]:
        directory = root / "testdata" / name
        directory.mkdir(parents=True, exist_ok=True)
        for i in range(1, count + 1):
            (directory / f"{i}.in").write_text(f"{i} {i + 1}\n", encoding="ascii")
            (directory / f"{i}.out").write_text(f"{2 * i + 1}\n", encoding="ascii")
    template = '''#include <cstdio>
#include <iostream>
using namespace std;
int main() {{
    freopen("{name}.in", "r", stdin);
    {body}
}}
'''
    for student in ("HBCSP26001", "HBCSP26002", "HBCSP26003"):
        for name in ("apple", "road", "tree", "game"):
            body = f'freopen("{name}.out", "w", stdout); long long a,b; cin>>a>>b; cout<<a+b<<"\\n"; return 0;'
            if student == "HBCSP26002":
                body = {"apple": 'freopen("apple.out","w",stdout); long long a,b; cin>>a>>b; cout<<a+b+1; return 0;',
                        "road": "this is a syntax error;", "tree": "volatile unsigned x=0; for(;;) ++x;",
                        "game": 'cout<<"console output is not game.out"; return 0;'}[name]
            if student == "HBCSP26003":
                if name == "road":
                    continue
                if name == "apple":
                    body = 'long long a,b; cin>>a>>b; if(a==1){freopen("apple.out","w",stdout); cout<<a+b;} return 0;'
                if name == "tree":
                    body = "return 17;"
            folder = root / "submissions" / student / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{name}.cpp").write_text(template.format(name=name, body=body), encoding="utf-8")


if __name__ == "__main__":
    make_demo(Path(__file__).resolve().parents[1] / "demo")
