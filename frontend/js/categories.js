const messageBox = document.getElementById("cat-message");
const tableBody = document.getElementById("cat-body");
const table = document.getElementById("cat-table");
const emptyNote = document.getElementById("cat-empty");
const nameInput = document.getElementById("cat-name");

let categories = new Map();

async function load() {
  try {
    const list = await api.listCategories();
    categories = new Map(list.map((c) => [c.id, c.name]));
    table.hidden = list.length === 0;
    emptyNote.hidden = list.length !== 0;
    tableBody.innerHTML = list
      .map(
        (c) => `
        <tr>
          <td>${escapeHtml(c.name)}</td>
          <td class="row-actions">
            <button class="small secondary" data-action="rename" data-id="${c.id}">Rename</button>
            <button class="small danger" data-action="delete" data-id="${c.id}">Delete</button>
          </td>
        </tr>`
      )
      .join("");
  } catch (err) {
    showMessage(messageBox, err.message, "error");
  }
}

document.getElementById("cat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(messageBox);
  try {
    await api.createCategory(nameInput.value);
    nameInput.value = "";
    await load();
  } catch (err) {
    showMessage(messageBox, err.message, "error");
  }
});

tableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const currentName = categories.get(id);
  hideMessage(messageBox);

  try {
    if (button.dataset.action === "rename") {
      const newName = prompt("New name for this category:", currentName);
      if (newName === null || newName.trim() === "" || newName.trim() === currentName) return;
      await api.renameCategory(id, newName);
      await load();
    } else if (button.dataset.action === "delete") {
      if (!confirm(`Delete the category "${currentName}"?`)) return;
      await api.deleteCategory(id);
      await load();
    }
  } catch (err) {
    showMessage(messageBox, err.message, "error");
  }
});

function init() {
  if (!requireLogin()) return;
  renderNav("categories");
  load();
}
init();
