// Minimal stand-in for the design tool runtime, so docs/design/*.dc.html render in a plain browser.
// QA-only (apps/quoteshop/docs/qa/render). Props: defaults from data-props, override via URL query (?dark=1&accent=%23B4372A).
(() => {
  document.head.insertAdjacentHTML('beforeend', '<style>x-dc:not([data-ready]){display:none}x-dc{display:contents}</style>');

  const lit = /^(true|false|null|-?\d+(\.\d+)?|"[^"]*")$/;
  const val = (expr, scope) => {
    const e = String(expr).replace(/^\s*\{\{|\}\}\s*$/g, '').trim();
    if (lit.test(e)) return JSON.parse(e);
    return e.split('.').reduce((o, k) => (o == null ? undefined : o[k]), scope);
  };
  const sub = (s, scope) => s.replace(/\{\{([^}]*)\}\}/g, (_, e) => { const v = val(e, scope); return v == null ? '' : String(v); });
  const evt = (name, el) => {
    const n = name.slice(2).toLowerCase();
    return n === 'change' && /^(INPUT|TEXTAREA)$/.test(el.tagName) ? 'input' : n; // React-style onChange
  };

  // Walk the (inert) template tree and build live DOM: <template data-sc=for|if> = sc-for / sc-if.
  function expand(src, scope) {
    const out = document.createDocumentFragment();
    for (const n of src.childNodes) {
      if (n.nodeType === 3) { out.append(sub(n.data, scope)); continue; }
      if (n.nodeType !== 1) continue;
      const kind = n.tagName === 'TEMPLATE' && n.dataset.sc;
      if (kind === 'for') {
        const as = n.getAttribute('as');
        [...(val(n.getAttribute('list'), scope) || [])].forEach((item, i) => out.append(expand(n.content, { ...scope, [as]: item, $index: i })));
        continue;
      }
      if (kind === 'if') { if (val(n.getAttribute('value'), scope)) out.append(expand(n.content, scope)); continue; }
      const el = document.importNode(n, false);
      for (const a of [...el.attributes]) {
        if (/^on/i.test(a.name)) {
          const fn = val(a.value, scope);
          el.removeAttribute(a.name);
          if (typeof fn === 'function') el.addEventListener(evt(a.name, el), fn);
        } else if (a.value.includes('{{')) el.setAttribute(a.name, sub(a.value, scope));
      }
      el.append(expand(n.tagName === 'TEMPLATE' ? n.content : n, scope));
      out.append(el);
    }
    return out;
  }

  class DCLogic {
    constructor(props) { this.props = props; this.state = {}; }
    setState(patch) {
      this.state = { ...this.state, ...(typeof patch === 'function' ? patch(this.state, this.props) : patch) };
      window.dc.render();
    }
  }

  async function boot() {
    const root = document.querySelector('x-dc');
    // Raw source, because the HTML parser foster-parents <sc-for> out of <tbody>. file:// falls back to the parsed DOM.
    const raw = await fetch(location.href).then((r) => r.text()).catch(() => '<x-dc>' + root.innerHTML + '</x-dc>');
    let body = (raw.match(/<x-dc>([\s\S]*)<\/x-dc>/) || [, ''])[1];
    body = body.replace(/<helmet>([\s\S]*?)<\/helmet>/g, (_, css) => { document.head.insertAdjacentHTML('beforeend', css); return ''; });
    const tpl = document.createElement('template');
    tpl.innerHTML = body.replace(/<sc-(for|if)\b/g, '<template data-sc="$1"').replace(/<\/sc-(for|if)>/g, '</template>');

    const script = document.querySelector('script[data-dc-script]');
    const meta = JSON.parse(script.dataset.props || '{}');
    const props = {};
    for (const [k, v] of Object.entries(meta)) if (k[0] !== '$') props[k] = v && v.default;
    for (const [k, v] of new URLSearchParams(location.search)) props[k] = /^(1|true)$/.test(v) ? true : /^(0|false)$/.test(v) ? false : v;

    const Component = new Function('DCLogic', script.textContent + '\nreturn Component;')(DCLogic);
    const inst = new Component(props);
    window.dc = {
      instance: inst, props, tpl, preview: meta.$preview,
      render() { root.replaceChildren(expand(tpl.content, inst.renderVals())); root.dataset.ready = ''; },
    };
    window.dc.render();
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', boot) : boot();
})();
