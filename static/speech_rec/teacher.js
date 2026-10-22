(function () {
  const headers = { "Content-Type": "application/json", "X-Speech-Rec-Request": "1" };
  let currentId = "";

  async function saveFlags() {
    await fetch("/rec/api/t/settings", {
      method: "POST",
      headers,
      body: JSON.stringify({
        student_enabled: document.getElementById("enabled").checked,
        id_fields: { enabled: document.getElementById("id-on").checked },
      }),
    });
  }
  document.getElementById("enabled").onchange = saveFlags;
  document.getElementById("id-on").onchange = saveFlags;

  document.getElementById("make").onsubmit = async (event) => {
    event.preventDefault();
    document.getElementById("err").textContent = "";
    const res = await fetch("/rec/api/t/assignments", {
      method: "POST",
      headers,
      body: JSON.stringify({
        text: document.getElementById("text").value,
        prep_sec: Number(document.getElementById("prep").value),
        speak_sec: Number(document.getElementById("speak").value),
        ttl_hours: Number(document.getElementById("ttl").value),
        max_submissions: Number(document.getElementById("limit").value),
        label: document.getElementById("label").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      document.getElementById("err").textContent = "作れませんでした。お題と秒数を確認してください。";
      return;
    }
    currentId = data.id;
    document.getElementById("out").innerHTML = `
      <p><a href="${data.url}">${data.url}</a></p>
      <img alt="提出用QR" src="${data.qr}">
      <div class="live" id="live"></div>
      <button id="close" type="button">終了</button>`;
    document.getElementById("close").onclick = async () => {
      await fetch(`/rec/api/t/assignments/${currentId}/close`, { method: "POST", headers });
      refresh();
    };
    refresh();
  };

  async function refresh() {
    if (!currentId) return;
    const res = await fetch(`/rec/api/t/assignments/${currentId}/live`, { headers });
    const data = await res.json();
    const node = document.getElementById("live");
    if (!node) return;
    node.textContent = `受付 ${data.received}　処理中 ${data.processing}　完了 ${data.done}　エラー ${data.error}`;
  }
  setInterval(refresh, 10000);
})();
