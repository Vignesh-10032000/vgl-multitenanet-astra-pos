// ============================================================
// மாணிக்கம் ஸ்டோர்ஸ் POS — Shared JS Utilities
// Tamil Nadu · GST Ready · ₹ Indian Rupee
// ============================================================

// Indian Rupee formatter (₹1,00,000 Indian number system)
function fmt(amount) {
  if (amount == null || isNaN(amount)) return '₹0.00';
  return '₹' + Number(amount).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

// Payment method label (Tamil + English)
function payLabel(method) {
  const labels = { cash: '💵 ரொக்கம்', upi: '📱 UPI', card: '💳 Card', mobile: '📱 UPI' };
  return labels[method] || method;
}

// Live Clock (IST)
function updateClock() {
  const el = document.getElementById('timeDisplay');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
updateClock();
setInterval(updateClock, 1000);

// Sidebar Toggle
const sidebar = document.getElementById('sidebar');
const mainContent = document.getElementById('mainContent');
const sidebarToggle = document.getElementById('sidebarToggle');
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('sidebar-collapsed');
  });
}

// Modal helpers
function openModal(id) {
  const modal = document.getElementById(id);
  const backdrop = document.getElementById('modalBackdrop');
  if (modal) { modal.classList.add('open'); backdrop.classList.add('open'); document.body.style.overflow = 'hidden'; }
}
function closeModal(id) {
  const modal = document.getElementById(id);
  const backdrop = document.getElementById('modalBackdrop');
  if (modal) { modal.classList.remove('open'); backdrop.classList.remove('open'); document.body.style.overflow = ''; }
}
document.getElementById('modalBackdrop').addEventListener('click', () => {
  document.querySelectorAll('.modal.open').forEach(m => closeModal(m.id));
});

// Toast notification
function showToast(message, type = 'info', duration = 3000) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span class="toast-msg">${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.classList.add('visible'), 10);
  setTimeout(() => { toast.classList.remove('visible'); setTimeout(() => toast.remove(), 300); }, duration);
}
