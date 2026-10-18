/* Мини-рендерер Markdown для DanirAI (без внешних библиотек). */
(function (global) {
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function inline(text) {
    return text
      .replace(/`([^`]+)`/g, function (_, c) { return '<code>' + c + '</code>'; })
      .replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/~~([^~]+)~~/g, '<s>$1</s>')
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }

  function table(lines, i) {
    // i указывает на строку заголовка; i+1 — разделитель
    var header = lines[i].split('|').map(function (c) { return c.trim(); }).filter(function (c, idx, a) { return !(idx === 0 && c === '') && !(idx === a.length - 1 && c === ''); });
    var rows = [];
    var j = i + 2;
    while (j < lines.length && lines[j].indexOf('|') !== -1 && lines[j].trim() !== '') {
      rows.push(lines[j].split('|').map(function (c) { return c.trim(); }).filter(function (c, idx, a) { return !(idx === 0 && c === '') && !(idx === a.length - 1 && c === ''); }));
      j++;
    }
    var html = '<table><thead><tr>' + header.map(function (h) { return '<th>' + inline(escapeHtml(h)) + '</th>'; }).join('') + '</tr></thead><tbody>';
    rows.forEach(function (r) {
      html += '<tr>' + header.map(function (_, k) { return '<td>' + inline(escapeHtml(r[k] || '')) + '</td>'; }).join('') + '</tr>';
    });
    return { html: html + '</tbody></table>', next: j };
  }

  function render(src) {
    if (!src) return '';
    var blocks = [];
    // вырезаем блоки кода
    src = String(src).replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
      blocks.push('<pre><code data-lang="' + escapeHtml(lang) + '">' + escapeHtml(code.replace(/\n$/, '')) + '</code></pre>');
      return '\u0000CODE' + (blocks.length - 1) + '\u0000';
    });

    var lines = src.split('\n');
    var out = [];
    var listType = null;
    var para = [];

    function flushPara() {
      if (para.length) {
        out.push('<p>' + para.map(function (p) { return inline(escapeHtml(p)); }).join('<br>') + '</p>');
        para = [];
      }
    }
    function flushList() {
      if (listType) { out.push('</' + listType + '>'); listType = null; }
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var m;

      if (/^\s*\u0000CODE\d+\u0000\s*$/.test(line)) {
        flushPara(); flushList();
        out.push(line.trim());
        continue;
      }
      if (line.trim() === '') { flushPara(); flushList(); continue; }

      if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
        flushPara(); flushList();
        var lvl = m[1].length;
        out.push('<h' + lvl + '>' + inline(escapeHtml(m[2])) + '</h' + lvl + '>');
        continue;
      }
      if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) { flushPara(); flushList(); out.push('<hr>'); continue; }
      if ((m = line.match(/^>\s?(.*)$/))) {
        flushList();
        out.push('<blockquote>' + inline(escapeHtml(m[1])) + '</blockquote>');
        continue;
      }
      if (line.indexOf('|') !== -1 && i + 1 < lines.length && /^\s*\|?[\s:-]+\|[-\s|:]+\|?\s*$/.test(lines[i + 1])) {
        flushPara(); flushList();
        var t = table(lines, i);
        out.push(t.html);
        i = t.next - 1;
        continue;
      }
      if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
        flushPara();
        if (listType !== 'ul') { flushList(); out.push('<ul>'); listType = 'ul'; }
        out.push('<li>' + inline(escapeHtml(m[1])) + '</li>');
        continue;
      }
      if ((m = line.match(/^\s*(\d+)[.)]\s+(.*)$/))) {
        flushPara();
        if (listType !== 'ol') { flushList(); out.push('<ol>'); listType = 'ol'; }
        out.push('<li>' + inline(escapeHtml(m[2])) + '</li>');
        continue;
      }
      para.push(line);
    }
    flushPara(); flushList();

    var html = out.join('\n');
    html = html.replace(/\u0000CODE(\d+)\u0000/g, function (_, idx) { return blocks[+idx]; });
    return html;
  }

  global.DanirMarkdown = { render: render, escapeHtml: escapeHtml };
})(window);
