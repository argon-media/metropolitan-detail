#!/usr/bin/env python3
"""
Metropolitan Detail — static build for the Claude Design export -> clean-route site.

WHAT IT DOES
  Turns the Claude Design "Project archive" export (.dc.html files) into the deployed
  clean-route static site that lives in this repo and auto-deploys to Vercel on push.
  Per page it: picks the clean slug (Home -> index/"/"), injects canonical + OG/Twitter
  meta after <title>, makes og:image absolute, and rewrites internal `X.dc.html` links
  to `/slug`. Only pages that ALREADY exist as committed <slug>.html are rebuilt
  (Variations / Style Guide / stubs are skipped); revisit the allowlist logic if the
  client adds a genuinely new page.

USAGE
  1. Unzip the export somewhere, e.g.:
       unzip -o "~/Downloads/# Metropolitan Detail.zip" -d /tmp/md-export
     (the .dc.html live at the top level of that folder, alongside uploads/)
  2. Build the HTML in place (writes <slug>.html into the repo root):
       python3 scripts/build.py /tmp/md-export
     or to a staging dir first (recommended — diff before you copy over):
       python3 scripts/build.py /tmp/md-export /tmp/md-staging
  3. Resolve new uploads referenced by the build (reports + optionally copies):
       python3 scripts/build.py /tmp/md-export --uploads
     Copies referenced images that are in the export but not yet in the repo
     (incl. uploads/thumbs/*). It NEVER writes over the root-level Tesla*/Porsche*
     gallery files (macOS case-collision trap) and does no git operations.
  4. Review, then stage EXPLICIT paths only and commit:
       git add -- <the changed .html> uploads/<new files>
       # NEVER `git add -A` — capitalized Tesla*/Porsche* show as modified and
       # staging them re-breaks the DYNOmatte gallery. Leave them unstaged.
       git commit && git push   # Vercel auto-deploys from main

VALIDATION
  Reconstructed + validated 2026-09-15: regenerating the live pages differed from the
  committed output ONLY in intended content (meta/canonical/og/links reproduced 1:1).
"""
import os, re, sys, html, glob, zipfile, shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://metropolitandetail.argon-devsite.com"


def slugify(dcname):
    n = dcname[:-len(".dc.html")] if dcname.endswith(".dc.html") else dcname
    if n.strip().lower() == "home":
        return "index"
    return re.sub(r"[^a-z0-9]+", "-", n.lower().strip()).strip("-")


def committed_pages():
    # allowlist = clean routes that already exist in the repo root
    return {os.path.basename(p) for p in glob.glob(os.path.join(REPO, "*.html"))}


def dc_routes(export):
    m = {}
    for p in glob.glob(os.path.join(export, "*.dc.html")):
        b = os.path.basename(p)
        s = slugify(b)
        m[b] = "/" if s == "index" else "/" + s
    return m


def abs_upload(u):
    u = u.strip()
    return u if u.startswith("http") else BASE + "/" + u.lstrip("./").lstrip("/")


def build_html(export, out):
    committed = committed_pages()
    routes = dc_routes(export)

    def rewrite_links(s):
        def repl(m):
            t = m.group(1)
            r = routes.get(t)
            if r is None:
                r = "/" if t.lower().startswith("home") else "/" + slugify(t)
            return 'href="' + r + '"'
        return re.sub(r'href="([^"]+\.dc\.html)"', repl, s)

    def val(s, pat):
        m = re.search(pat, s, re.I)
        return m.group(1) if m else None

    os.makedirs(out, exist_ok=True)
    built = []
    for p in sorted(glob.glob(os.path.join(export, "*.dc.html"))):
        b = os.path.basename(p)
        slug = slugify(b)
        fn = slug + ".html"
        if fn not in committed:
            continue
        src = open(p, encoding="utf-8", errors="replace").read()
        canonical = BASE + "/" if slug == "index" else BASE + "/" + slug
        title = val(src, r"<title>(.*?)</title>") or "Metropolitan Detail"
        desc = val(src, r'<meta name="description" content="(.*?)"') or ""
        og_src = val(src, r'<meta property="og:image" content="(.*?)"') or "uploads/og-share.jpg"
        if slug == "index":
            social = BASE + "/uploads/og-share.jpg"
            dims = ('<meta property="og:image:width" content="1200">\n'
                    '<meta property="og:image:height" content="630">\n')
        else:
            social = abs_upload(og_src)
            dims = ""
        alt = html.escape(title)  # double-escapes &amp; in title, matching prior output
        inject = (
            f'<link rel="canonical" href="{canonical}">\n'
            f'<meta name="robots" content="index, follow">\n'
            f'<meta name="theme-color" content="#0a0a0a">\n'
            f'<meta property="og:site_name" content="Metropolitan Detail">\n'
            f'<meta property="og:url" content="{canonical}">\n'
            f'<meta property="og:locale" content="en_US">\n'
            f'<meta property="og:image" content="{social}">\n'
            f'<meta property="og:image:secure_url" content="{social}">\n'
            f'<meta property="og:image:alt" content="{alt}">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<meta name="twitter:title" content="{alt}">\n'
            f'<meta name="twitter:description" content="{desc}">\n'
            f'<meta name="twitter:image" content="{social}">\n' + dims
        )
        o = re.sub(r"(</title>\n)", lambda m: m.group(1) + inject, src, count=1)
        o = re.sub(r'(<meta property="og:image" content=")([^"]+)(">)',
                   lambda m: m.group(1) + abs_upload(m.group(2)) + m.group(3), o)
        o = rewrite_links(o)
        open(os.path.join(out, fn), "w", encoding="utf-8").write(o)
        built.append(fn)
    return built


def _index_export_uploads(export):
    """Return {relpath 'uploads/..' -> zip-entry-name or fs-path} and {stem -> relpath-from-uploads}.
    `export` may be a .zip or an unzipped directory."""
    exp_rel, exp_stem = {}, {}
    if export.endswith(".zip"):
        with zipfile.ZipFile(export) as z:
            for n in z.namelist():
                i = n.find("uploads/")
                if i < 0 or n.endswith("/"):
                    continue
                rel = n[i:]
                exp_rel[rel] = n
                exp_stem.setdefault(os.path.splitext(os.path.basename(rel))[0], rel[len("uploads/"):])
    else:
        for p in glob.glob(os.path.join(export, "uploads", "**", "*"), recursive=True):
            if os.path.isdir(p):
                continue
            rel = "uploads/" + os.path.relpath(p, os.path.join(export, "uploads"))
            exp_rel[rel] = p
            exp_stem.setdefault(os.path.splitext(os.path.basename(p))[0], rel[len("uploads/"):])
    return exp_rel, exp_stem


def _read_export_bytes(export, entry):
    if export.endswith(".zip"):
        with zipfile.ZipFile(export) as z:
            return z.read(entry)
    return open(entry, "rb").read()


def resolve_uploads(export, out, copy=False):
    """Report (and optionally copy) uploads referenced by built pages but not yet in the repo.
    Resolves explicit `uploads/X.ext` refs and bare-stem gallery arrays against the export.
    Never overwrites an existing file, so the Tesla*/Porsche* collision set is untouched.
    Does no git operations — staging/commit stays a reviewed manual step."""
    exp_rel, exp_stem = _index_export_uploads(export)
    tracked = set()
    for p in glob.glob(os.path.join(REPO, "uploads", "**", "*"), recursive=True):
        if os.path.isfile(p):
            tracked.add("uploads/" + os.path.relpath(p, os.path.join(REPO, "uploads")))
    refs = set()
    EXT = r"(?:jpe?g|png|webp|gif|svg|mp4|webm|avif)"
    for p in glob.glob(os.path.join(out, "*.html")):
        s = open(p, encoding="utf-8", errors="replace").read()
        # quote-delimited attrs (space-safe: filenames like "BMW Z4 (2) (1).jpg" are common)
        for m in re.findall(r'(?:src|href|content|data-src|poster)="(uploads/[^"]+\.' + EXT + r')"', s, re.I):
            refs.add(m)
        for m in re.findall(r"(?:src|href|content|data-src|poster)='(uploads/[^']+\." + EXT + r")'", s, re.I):
            refs.add(m)
        # css url(...) with optional quotes
        for m in re.findall(r"url\(\s*['\"]?(uploads/[^)'\"]+\." + EXT + r")['\"]?\s*\)", s, re.I):
            refs.add(m)
        # bare tokens as a fallback (no spaces) — catches odd inline refs
        for m in re.findall(r'uploads/([^\s"\')]+\.' + EXT + r')', s, re.I):
            refs.add("uploads/" + m)
        # gallery JS bare-stem arrays: ['IMG_2463-1','BMW Z4 (2)'].forEach(...'uploads/'+n+'.jpg')
        for arr in re.findall(r"\[([^\]]*?)\]\s*\.\s*(?:forEach|map)", s):
            for st in re.findall(r"['\"]([^'\"/]+)['\"]", arr):
                if "." not in st and st in exp_stem:
                    refs.add("uploads/" + exp_stem[st])
    new = sorted(r for r in refs if r not in tracked and r in exp_rel)
    missing = sorted(r for r in refs if r not in tracked and r not in exp_rel)
    print(f"referenced: {len(refs)}  |  new (in export, not in repo): {len(new)}  |  unresolved: {len(missing)}")
    for r in new:
        print("   +", r)
        if copy:
            dst = os.path.join(REPO, r)
            if os.path.exists(dst):
                continue  # never overwrite (collision safety)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(_read_export_bytes(export, exp_rel[r]))
    if copy and new:
        print(f"\ncopied {len(new)} new uploads. Now stage EXPLICIT paths (never `git add -A`):")
        print("   git add -- <changed .html> " + " ".join(f'"{r}"' for r in new))
    return new


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    export = os.path.expanduser(sys.argv[1])
    rest = sys.argv[2:]
    do_uploads = "--uploads" in rest
    copy = "--copy" in rest or "--uploads" in rest
    out = next((a for a in rest if not a.startswith("--")), REPO)
    if do_uploads:
        # when only resolving uploads, build into a temp so refs are current
        built = build_html(export, out)
        print(f"built {len(built)} pages -> {out}")
        resolve_uploads(export, out, copy=copy)
    else:
        built = build_html(export, out)
        print(f"built {len(built)} pages -> {out}")
