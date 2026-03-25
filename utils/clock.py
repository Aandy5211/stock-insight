"""世界时钟组件 — 通过 JS 注入父页面右上角，显示北京 & 纽约实时时间"""
import streamlit.components.v1 as components


def show_world_clock() -> None:
    """在页面右上角注入实时双城时钟浮层（通过 iframe→parent DOM 注入）"""

    components.html("""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<script>
(function () {
    var P = window.parent.document;

    /* ── 避免重复注入 ── */
    if (P.getElementById('wc-root')) return;

    /* ── 样式 ── */
    var css = P.createElement('style');
    css.id = 'wc-style';
    css.textContent = [
        '#wc-root{',
            'position:fixed;top:58px;right:14px;z-index:99999;',
            'font-family:"Segoe UI","PingFang SC",system-ui,sans-serif;',
        '}',
        '#wc-card{',
            'background:linear-gradient(145deg,rgba(8,14,40,.92),rgba(18,26,66,.92));',
            'backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);',
            'border-radius:14px;padding:9px 15px 10px;',
            'border:1px solid rgba(110,140,255,.22);',
            'box-shadow:0 8px 28px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.07);',
            'min-width:190px;user-select:none;',
        '}',
        '#wc-hdr{',
            'text-align:center;color:rgba(170,185,255,.4);',
            'font-size:.5em;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:8px;',
        '}',
        '.wc-row{display:flex;align-items:center;}',
        '.wc-city{flex:1;text-align:center;padding:0 4px;}',
        '.wc-flag{font-size:.9em;line-height:1;margin-bottom:3px;}',
        '.wc-lbl{font-size:.52em;font-weight:600;letter-spacing:1.5px;margin-bottom:3px;}',
        '.wc-t{',
            'font-size:1.05em;font-weight:700;color:#fff;',
            'font-variant-numeric:tabular-nums;letter-spacing:1px;',
            'text-shadow:0 0 14px rgba(100,150,255,.35);',
        '}',
        '.wc-d{font-size:.46em;color:rgba(190,205,255,.38);margin-top:3px;}',
        '.wc-sep{',
            'width:1px;height:44px;flex-shrink:0;',
            'background:linear-gradient(to bottom,transparent,rgba(120,150,255,.22),transparent);',
        '}',
    ].join('');
    P.head.appendChild(css);

    /* ── DOM 结构 ── */
    var root = P.createElement('div');
    root.id = 'wc-root';
    root.innerHTML =
        '<div id="wc-card">' +
            '<div id="wc-hdr">&#9202; World Clock</div>' +
            '<div class="wc-row">' +
                '<div class="wc-city">' +
                    '<div class="wc-flag">&#127464;&#127475;</div>' +
                    '<div class="wc-lbl" style="color:#7eb8f7;">北 京</div>' +
                    '<div class="wc-t" id="wc-bj-t">--:--:--</div>' +
                    '<div class="wc-d" id="wc-bj-d">&nbsp;</div>' +
                '</div>' +
                '<div class="wc-sep"></div>' +
                '<div class="wc-city">' +
                    '<div class="wc-flag">&#127482;&#127480;</div>' +
                    '<div class="wc-lbl" style="color:#f48fb1;">纽 约</div>' +
                    '<div class="wc-t" id="wc-ny-t">--:--:--</div>' +
                    '<div class="wc-d" id="wc-ny-d">&nbsp;</div>' +
                '</div>' +
            '</div>' +
        '</div>';
    P.body.appendChild(root);

    /* ── 时钟逻辑 ── */
    var DAYS = ['周日','周一','周二','周三','周四','周五','周六'];
    function pad(n){ return n < 10 ? '0'+n : ''+n; }
    function fmtT(d){ return pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds()); }
    function fmtD(d){ return (d.getMonth()+1)+'月'+d.getDate()+'日 '+DAYS[d.getDay()]; }
    function set(id, v){ var e=P.getElementById(id); if(e && e.innerText!==v) e.innerText=v; }

    function tick(){
        var now = new Date();
        var bj = new Date(now.toLocaleString('en-US',{timeZone:'Asia/Shanghai'}));
        var ny = new Date(now.toLocaleString('en-US',{timeZone:'America/New_York'}));
        set('wc-bj-t', fmtT(bj)); set('wc-bj-d', fmtD(bj));
        set('wc-ny-t', fmtT(ny)); set('wc-ny-d', fmtD(ny));
    }

    tick();
    setInterval(tick, 1000);

    /* ── 隐藏 Streamlit Cloud Status / Manage App 浮层 ── */
    function hideStatusWidget() {
        var selectors = [
            'iframe[title="Streamlit Cloud Status"]',
            '[data-testid="stStatusWidget"]',
            'button[title="Manage app"]',
            'button[aria-label="Manage app"]',
        ];
        selectors.forEach(function(sel) {
            P.querySelectorAll(sel).forEach(function(el) {
                el.style.setProperty('display', 'none', 'important');
            });
        });
    }
    hideStatusWidget();
    /* 监听 DOM 变化，防止按钮动态插入后重新出现 */
    var observer = new MutationObserver(hideStatusWidget);
    observer.observe(P.body, { childList: true, subtree: true });
})();
</script>
</body>
</html>
""", height=0, scrolling=False)
