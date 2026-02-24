/**
 * Script injected into the preview iframe to detect clicks on elements
 * with data-node-id attributes and relay them to the parent window.
 */
export function getIframeInjectionScript(): string {
  return `
<script>
(function() {
  var hovered = null;

  document.addEventListener('mouseover', function(e) {
    var target = e.target.closest('[data-node-id]');
    if (hovered && hovered !== target) {
      hovered.style.outline = '';
      hovered.style.outlineOffset = '';
    }
    if (target) {
      target.style.outline = '2px solid rgba(59,130,246,0.5)';
      target.style.outlineOffset = '-2px';
      hovered = target;
    }
  });

  document.addEventListener('mouseout', function(e) {
    if (hovered) {
      hovered.style.outline = '';
      hovered.style.outlineOffset = '';
      hovered = null;
    }
  });

  document.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    var target = e.target.closest('[data-node-id]');
    if (!target) return;

    var rect = target.getBoundingClientRect();
    var cs = window.getComputedStyle(target);
    var computedStyles = {
      marginTop: cs.marginTop,
      marginRight: cs.marginRight,
      marginBottom: cs.marginBottom,
      marginLeft: cs.marginLeft,
      paddingTop: cs.paddingTop,
      paddingRight: cs.paddingRight,
      paddingBottom: cs.paddingBottom,
      paddingLeft: cs.paddingLeft
    };

    var href = '';
    var linkTarget = '';
    if (target.tagName.toLowerCase() === 'a') {
      href = target.getAttribute('href') || '';
      linkTarget = target.getAttribute('target') || '';
    } else {
      var parentLink = target.closest('a');
      if (parentLink) {
        href = parentLink.getAttribute('href') || '';
        linkTarget = parentLink.getAttribute('target') || '';
      }
    }

    window.parent.postMessage({
      type: 'node-click',
      nodeId: target.getAttribute('data-node-id'),
      tagName: target.tagName.toLowerCase(),
      textContent: target.innerText || '',
      className: target.className || '',
      rect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height
      },
      computedStyles: computedStyles,
      href: href,
      target: linkTarget
    }, '*');
  }, true);

  window.addEventListener('message', function(e) {
    if (!e.data || e.data.type !== 'get-layout-info' || !e.data.nodeId) return;
    var el = document.querySelector('[data-node-id="' + e.data.nodeId + '"]');
    if (!el) return;
    var cs = window.getComputedStyle(el);
    var parent = el.parentElement;
    var pcs = parent ? window.getComputedStyle(parent) : null;
    var pRect = parent ? parent.getBoundingClientRect() : null;
    var elRect = el.getBoundingClientRect();
    window.parent.postMessage({
      type: 'layout-info-response',
      nodeId: e.data.nodeId,
      rect: { x: elRect.x, y: elRect.y, width: elRect.width, height: elRect.height },
      parentRect: pRect ? { x: pRect.x, y: pRect.y, width: pRect.width, height: pRect.height } : null,
      layoutInfo: {
        position: cs.position,
        display: cs.display,
        parentDisplay: pcs ? pcs.display : '',
        parentFlexDirection: pcs ? pcs.flexDirection : '',
        existingTransform: cs.transform,
        hasExistingLeft: cs.left !== 'auto',
        hasExistingTop: cs.top !== 'auto',
        computedLeft: parseFloat(cs.left) || 0,
        computedTop: parseFloat(cs.top) || 0
      }
    }, '*');
  });
})();
</script>`;
}

/**
 * Rewrites asset URLs in HTML so they resolve via the backend API.
 */
export function rewriteAssetUrls(html: string, baseUrl: string): string {
  return html
    .replace(/src="assets\//g, `src="${baseUrl}/assets/`)
    .replace(/src='assets\//g, `src='${baseUrl}/assets/`)
    .replace(/url\("assets\//g, `url("${baseUrl}/assets/`)
    .replace(/url\('assets\//g, `url('${baseUrl}/assets/`);
}

/**
 * Builds the full srcdoc HTML that goes into the preview iframe.
 */
export function buildSrcdoc(
  html: string,
  css: string,
  assetBaseUrl: string
): string {
  let rewritten = rewriteAssetUrls(html, assetBaseUrl);

  const cssLink = rewritten.match(/<link[^>]*styles\.css[^>]*>/i);
  if (cssLink) {
    const inlineStyle = `<style>${css}</style>`;
    rewritten = rewritten.replace(cssLink[0], inlineStyle);
  } else if (!rewritten.includes(css.slice(0, 60))) {
    const rewrittenCss = css
      .replace(/url\("assets\//g, `url("${assetBaseUrl}/assets/`)
      .replace(/url\('assets\//g, `url('${assetBaseUrl}/assets/`);
    rewritten = rewritten.replace(
      "</head>",
      `<style>${rewrittenCss}</style></head>`
    );
  }

  rewritten = rewritten.replace("</body>", `${getIframeInjectionScript()}</body>`);

  return rewritten;
}
