"""Patch Streamlit's index.html to eliminate FOUC.

Run this script after installing or upgrading Streamlit to inject the
SMA 2.0 background color into the framework's HTML shell.  This ensures
the browser paints #f5f9ff from the very first frame, before any Python
or JavaScript executes.

Usage:
    python patch_streamlit_index.py
"""

import os
import re
import sys


def find_index_html() -> str:
    import streamlit
    path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
    if not os.path.isfile(path):
        print(f"ERROR: index.html not found at {path}", file=sys.stderr)
        sys.exit(1)
    return path


ANTI_FOUC_BLOCK = """\
    <!-- SMA 2.0 anti-FOUC: paint #f5f9ff immediately, fade in 120ms after .stApp mounts -->
    <style>
      html, body, #root {
        background-color: #f5f9ff !important;
        margin: 0;
        padding: 0;
      }
      #root > div {
        opacity: 0;
        transition: opacity 0.2s ease;
      }
    </style>
    <script>
      // Reveal #root's child 120ms after .stApp mounts (gives CSS time to apply)
      document.addEventListener('DOMContentLoaded', function(){
        var root = document.getElementById('root');
        if (!root) return;
        var reveal = function(){
          var c = root.firstElementChild;
          if (c) c.style.opacity = '1';
        };
        var delayedReveal = function(){
          setTimeout(reveal, 120);
        };
        // If .stApp already exists (fast mount), reveal with delay
        if (root.querySelector('.stApp')) { delayedReveal(); return; }
        var mo = new MutationObserver(function(){
          if (root.querySelector('.stApp')) { delayedReveal(); mo.disconnect(); }
        });
        mo.observe(root, {childList:true, subtree:true, attributes:true});
        // Safety fallback
        setTimeout(reveal, 2500);
      });
    </script>"""

MARKER = "SMA 2.0 anti-FOUC"


def patch(path: str) -> None:
    content = open(path, encoding="utf-8").read()

    if MARKER in content:
        # Remove existing patch before re-applying (idempotent)
        content = re.sub(
            r"\s*<!-- SMA 2\.0 anti-FOUC.*?</script>",
            "",
            content,
            flags=re.DOTALL,
        )

    if "</head>" not in content:
        print("ERROR: could not locate </head> in index.html", file=sys.stderr)
        sys.exit(1)

    content = content.replace("</head>", f"{ANTI_FOUC_BLOCK}\n  </head>")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"OK: patched {path}")


if __name__ == "__main__":
    path = find_index_html()
    patch(path)
