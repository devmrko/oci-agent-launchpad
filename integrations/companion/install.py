"""Install the evidence view overlay into an explicitly selected Companion source checkout."""
import argparse
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout',type=Path)
    args=parser.parse_args()
    root=args.checkout.resolve()
    catalog=root/'src/main/java/io/github/devmrko/companion/web/CatalogPages.java'
    layout=root/'src/main/resources/templates/layout.html'
    code, html=catalog.read_text(),layout.read_text()
    marker='String destination=Set.of('
    nav='<p class="nav-group">인프라·운영</p>'
    if code.count(marker)!=1 or html.count(nav)!=1:
        parser.error('Unsupported Companion source structure; review before applying')
    code=code.replace(marker+'"/operations/tools"',marker+'"/delivery/evidence","/operations/tools"')
    if 'href="/delivery/evidence"' not in html:
        html=html.replace(nav,'<a class="side-item" href="/delivery/evidence" data-nav-path="/delivery" title="개발·실행 근거"><span class="nav-icon" aria-hidden="true">✓</span><span class="nav-text">개발·실행 근거</span></a>'+nav)
    for source in Path(__file__).with_name('src').rglob('*'):
        if source.is_file():
            target=root/'src'/source.relative_to(Path(__file__).with_name('src'))
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    catalog.write_text(code)
    layout.write_text(html)
    print('Evidence overlay installed. Build and test the selected checkout before running.')


if __name__=='__main__':
    main()
