import streamlit as st
import streamlit.components.v1 as components

def apply_custom_css_and_js():
    html = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
      html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3 {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
      }
      /* إخفاء أي عناصر tooltip مرئية */
      [role="tooltip"], .stTooltipHoverTarget, .stTooltipHoverTarget * {
        display: none !important;
        opacity: 0 !important;
        visibility: hidden !important;
        pointer-events: none !important;
      }
    </style>

    <script>
    (function() {
      // دالة لإزالة السمات المزعجة من عنصر واحد
      function stripAttrs(el) {
        if (!el) return;
        try {
          el.removeAttribute('title');
          el.removeAttribute('aria-label');
          el.removeAttribute('data-tooltip');
          el.removeAttribute('aria-describedby');
        } catch(e){}
      }

      // تنظيف أولي للعناصر الموجودة
      document.querySelectorAll('[title], [aria-label], [data-tooltip], [aria-describedby]').forEach(el => {
        const txt = (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('data-tooltip') || '');
        const bad = /expand|collapse|fullscreen|view|zoom|keyboard|more|less|open|close/i;
        if (bad.test(txt)) stripAttrs(el);
      });

      // مراقب أقوى يراقب التغييرات في الشجرة والسمات
      const observer = new MutationObserver(mutations => {
        for (const m of mutations) {
          if (m.type === 'attributes' && (m.attributeName === 'title' || m.attributeName === 'aria-label' || m.attributeName === 'data-tooltip' || m.attributeName === 'aria-describedby')) {
            stripAttrs(m.target);
          }
          if (m.addedNodes && m.addedNodes.length) {
            m.addedNodes.forEach(node => {
              if (!(node instanceof Element)) return;
              // إزالة سمات من العنصر المضاف وأطفاله
              node.querySelectorAll && node.querySelectorAll('[title], [aria-label], [data-tooltip], [aria-describedby]').forEach(stripAttrs);
              stripAttrs(node);
              // إزالة عناصر tooltip المرئية
              if (node.getAttribute && (node.getAttribute('role') === 'tooltip' || node.classList.contains('stTooltipHoverTarget'))) {
                try { node.remove(); } catch(e){}
              }
            });
          }
        }
      });

      observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['title','aria-label','data-tooltip','aria-describedby'] });

      // كإجراء احتياطي: فحص دوري قصير المدى للتأكد
      const interval = setInterval(() => {
        document.querySelectorAll('[title], [aria-label], [data-tooltip], [aria-describedby]').forEach(el => {
          stripAttrs(el);
        });
        document.querySelectorAll('[role="tooltip"], .stTooltipHoverTarget').forEach(el => {
          try { el.remove(); } catch(e){}
        });
      }, 800);

      // إيقاف الفحص بعد 20 ثانية لتقليل الحمل
      setTimeout(() => { clearInterval(interval); }, 20000);
    })();
    </script>
    """
    # height صغير لأننا لا نريد مساحة مرئية إضافية
    components.html(html, height=1, scrolling=False)

# استدعِ الدالة في بداية تطبيقك
apply_custom_css_and_js()
