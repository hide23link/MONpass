async function pageStudentQr() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 左: 発行フォーム -->
      <div class="bg-white rounded-2xl shadow p-6">
        <h2 class="text-xl font-bold text-sky-600 mb-4">QRを発行する</h2>
        <div id="remaining-badge" class="inline-block bg-sky-100 text-sky-700 text-sm font-medium px-3 py-1 rounded-full mb-4">読込中...</div>
        <div id="issue-form">
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-1">招待者名</label>
            <input id="guest-name" type="text"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-400"
              placeholder="例: お父さん、田中さん">
          </div>
          <div id="issue-error" class="hidden text-red-600 text-sm mb-3 p-2 bg-red-50 rounded-lg"></div>
          <button id="issue-btn"
            class="w-full bg-sky-500 hover:bg-sky-600 text-white font-bold py-2 rounded-lg transition disabled:opacity-50">
            発行する
          </button>
        </div>
        <div id="limit-reached" class="hidden text-gray-500 text-sm p-3 bg-gray-50 rounded-lg">
          上限（5枚）に達しました
        </div>
        <hr class="my-6">
        <div id="promote-section">
          <button id="promote-btn"
            class="w-full border border-sky-400 text-sky-600 hover:bg-sky-50 font-medium py-2 rounded-lg transition">
            🔑 管理者モードに切替
          </button>
        </div>
      </div>
      <!-- 右: 一覧 -->
      <div>
        <h2 class="text-xl font-bold text-sky-600 mb-4">発行済みQR一覧</h2>
        <div id="ticket-list" class="space-y-4">
          <div class="text-gray-400 text-sm">読込中...</div>
        </div>
      </div>
    </div>

    <!-- QR拡大モーダル -->
    <div id="qr-modal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="closeQrModal()">
      <div class="bg-white rounded-2xl p-5 w-full max-w-xs text-center" onclick="event.stopPropagation()">
        <img id="modal-qr-img" src="" alt="QR"
          style="width:100%; height:auto; display:block;"
          class="mx-auto mb-3 qr-img rounded">
        <p id="modal-guest-name" class="text-gray-700 font-medium text-sm mb-3"></p>
        <button onclick="closeQrModal()" class="bg-gray-200 hover:bg-gray-300 px-6 py-2 rounded-lg text-sm">閉じる</button>
      </div>
    </div>

    <!-- 昇格QRモーダル -->
    <div id="promote-modal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div class="bg-white rounded-2xl p-6 max-w-xs w-full text-center">
        <h3 class="text-lg font-bold text-sky-600 mb-2">管理者モード昇格</h3>
        <p class="text-sm text-gray-600 mb-4">管理者スマホでこのQRをスキャンしてください</p>
        <img id="promote-qr-img" src="" alt="昇格QR" class="w-48 h-48 mx-auto mb-4 qr-img">
        <button onclick="closePromoteModal()" class="bg-gray-200 hover:bg-gray-300 px-6 py-2 rounded-lg">閉じる</button>
      </div>
    </div>`;

  await loadStudentTickets();

  document.getElementById('issue-btn').addEventListener('click', issueTicket);
  document.getElementById('promote-btn').addEventListener('click', requestPromotion);
}

async function loadStudentTickets() {
  try {
    const tickets = await API.get('/ticket/list');
    const issued = tickets.length;
    const remaining = 5 - issued;

    const badge = document.getElementById('remaining-badge');
    if (badge) badge.textContent = `あと${remaining}枚発行できます`;

    const issueForm = document.getElementById('issue-form');
    const limitMsg  = document.getElementById('limit-reached');
    if (remaining <= 0) {
      issueForm && issueForm.classList.add('hidden');
      limitMsg  && limitMsg.classList.remove('hidden');
    } else {
      issueForm && issueForm.classList.remove('hidden');
      limitMsg  && limitMsg.classList.add('hidden');
    }

    const listEl = document.getElementById('ticket-list');
    if (!listEl) return;
    if (tickets.length === 0) {
      listEl.innerHTML = '<p class="text-gray-400 text-sm">まだ発行されていません</p>';
      return;
    }
    listEl.innerHTML = tickets.map(t => ticketCard(t)).join('');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function ticketCard(t) {
  const invalid = t.is_valid === 0;
  const used    = t.used === 1;

  let statusBadge;
  if (invalid) {
    statusBadge = `<span class="inline-block bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full">🚫 無効（管理者により無効化）</span>`;
  } else if (used) {
    statusBadge = `<span class="inline-block bg-green-100 text-green-700 text-xs px-2 py-0.5 rounded-full">✅ 入場済み</span>
       <span class="text-xs text-gray-500 ml-1">${formatDate(t.used_at)}</span>`;
  } else {
    statusBadge = `<span class="inline-block bg-sky-100 text-sky-700 text-xs px-2 py-0.5 rounded-full">⬜ 未入場</span>`;
  }

  // 削除ボタン: 未入場であれば有効・無効問わず削除可
  const deleteBtn = !used
    ? `<button onclick="deleteTicket('${t.ticket_id}')"
        class="text-red-500 hover:text-red-700 text-sm border border-red-300 hover:border-red-500 px-2 py-0.5 rounded transition">
        削除
      </button>`
    : '';

  // サムネイル: 幅固定・高さautoで縦横比を維持
  // onclick は this.src を使い base64 の二重埋め込みを避ける
  const imgStyle = invalid
    ? 'width:96px; height:auto; display:block; opacity:0.3;'
    : 'width:96px; height:auto; display:block; cursor:pointer;';
  const imgClass = 'qr-img rounded border border-gray-200';
  const imgClick = invalid
    ? ''
    : `onclick="openQrModal(this.src, '${escHtml(t.guest_name)}')"`;
  const imgEl = `<img src="${t.qr_image}" alt="QR" style="${imgStyle}" class="${imgClass}" ${imgClick}>`;

  // 無効チケットはカード背景を薄くする
  const cardClass = invalid
    ? 'bg-gray-50 rounded-xl shadow p-4 border border-red-100'
    : 'bg-white rounded-xl shadow p-4';

  return `
    <div class="${cardClass}" data-ticket-id="${t.ticket_id}">
      <div class="flex items-start gap-4">
        ${imgEl}
        <div class="flex-1 min-w-0">
          <p class="font-semibold ${invalid ? 'text-gray-400 line-through' : 'text-gray-800'} truncate">${escHtml(t.guest_name)}</p>
          <p class="text-xs text-gray-500 mb-1">発行: ${formatDate(t.created_at)}</p>
          <div class="mb-2">${statusBadge}</div>
          <div class="flex gap-2 flex-wrap">
            ${!invalid ? `<button onclick="saveQr('${t.qr_image}', '${escHtml(t.guest_name)}', '${t.ticket_id}', '${t.created_at}')"
              class="text-sky-600 hover:text-sky-800 text-sm border border-sky-300 hover:border-sky-500 px-2 py-0.5 rounded transition">
              画像を保存
            </button>` : ''}
            ${deleteBtn}
          </div>
        </div>
      </div>
    </div>`;
}

async function issueTicket() {
  const guestName = document.getElementById('guest-name').value.trim();
  const errEl = document.getElementById('issue-error');
  const btn   = document.getElementById('issue-btn');

  if (!guestName) {
    errEl.textContent = '招待者名を入力してください';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  errEl.classList.add('hidden');

  try {
    await API.post('/ticket/issue', { guest_name: guestName });
    document.getElementById('guest-name').value = '';
    showToast('QRを発行しました', 'success');
    await loadStudentTickets();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
  }
}

async function deleteTicket(ticketId) {
  if (!confirm('このQRチケットを削除しますか？')) return;
  try {
    await API.delete(`/ticket/${ticketId}`);
    showToast('削除しました', 'success');
    await loadStudentTickets();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function requestPromotion() {
  try {
    const data = await API.post('/promote/request', {});
    const img = document.getElementById('promote-qr-img');
    // サーバーが生成したQR画像をそのまま使用
    img.src = data.qr_image;
    document.getElementById('promote-modal').classList.remove('hidden');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function openQrModal(imgSrc, guestName) {
  document.getElementById('modal-qr-img').src = imgSrc;
  document.getElementById('modal-guest-name').textContent = guestName;
  document.getElementById('qr-modal').classList.remove('hidden');
}
function closeQrModal() { document.getElementById('qr-modal').classList.add('hidden'); }
function closePromoteModal() { document.getElementById('promote-modal').classList.add('hidden'); }

function saveQr(dataUrl, guestName, ticketId, createdAt) {
  // ファイル名に使えない文字を除去
  const sanitize = s => String(s).replace(/[\\/:*?"<>|\s]/g, '_');
  const filename = `QR_${sanitize(guestName)}.png`;

  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.click();
}

// シンプルなQR生成（promote用、html5-qrcodeのライブラリを使わずデータURLを返す）
async function generateQrDataUrl(text) {
  // バックエンドのQR生成エンドポイントを使う（シンプル実装: テキストをQRのURLとして使用）
  // ここでは promote_token を表示用にそのまま返す
  const canvas = document.createElement('canvas');
  canvas.width = 200; canvas.height = 200;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 200, 200);
  ctx.fillStyle = '#000'; ctx.font = '12px monospace';
  ctx.fillText('promote_token:', 10, 30);
  const words = text.split('?token=');
  if (words[1]) {
    for (let i = 0; i < words[1].length; i += 20) {
      ctx.fillText(words[1].slice(i, i+20), 10, 50 + Math.floor(i/20) * 16);
    }
  }
  return canvas.toDataURL('image/png');
}

// escHtml と formatDate は common.js で定義済み

function formatDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('ja-JP', { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' });
  } catch(_) { return iso; }
}
