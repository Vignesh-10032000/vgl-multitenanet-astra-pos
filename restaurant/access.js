const encoder = new TextEncoder();
export const ACCESS_KEY = "owner-access";
export const PASSWORD_ITERATIONS = 600000;
const hex = (bytes) =>
  [...new Uint8Array(bytes)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
function bytes(value) {
  return Uint8Array.from(value.match(/../g), (part) =>
    Number.parseInt(part, 16),
  );
}
export function validateAccount(account) {
  if (
    !account ||
    typeof account.username !== "string" ||
    !/^\S{3,64}$/u.test(account.username) ||
    !/^[a-f0-9]{32}$/.test(account.salt) ||
    !/^[a-f0-9]{64}$/.test(account.verifier) ||
    account.iterations !== PASSWORD_ITERATIONS
  )
    throw new Error("Invalid saved owner account");
  return account;
}
async function derive(password, account) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  return hex(
    await crypto.subtle.deriveBits(
      {
        name: "PBKDF2",
        salt: bytes(account.salt),
        iterations: account.iterations,
        hash: "SHA-256",
      },
      key,
      256,
    ),
  );
}
export async function createAccount(username, password) {
  username = String(username).trim().toLocaleLowerCase();
  if (!/^\S{3,64}$/u.test(username))
    throw new Error("Use a username with 3–64 characters and no spaces");
  if (
    typeof password !== "string" ||
    password.length < 10 ||
    password.length > 128
  )
    throw new Error("Use a password with 10–128 characters");
  const account = {
    username,
    salt: hex(crypto.getRandomValues(new Uint8Array(16))),
    iterations: PASSWORD_ITERATIONS,
  };
  account.verifier = await derive(password, account);
  return account;
}
export async function verifyAccount(account, username, password) {
  validateAccount(account);
  if (
    typeof username !== "string" ||
    typeof password !== "string" ||
    password.length > 128
  )
    return false;
  const candidate = await derive(password, account);
  let difference =
    username.trim().toLocaleLowerCase() === account.username ? 0 : 1;
  for (let i = 0; i < account.verifier.length; i++)
    difference |= candidate.charCodeAt(i) ^ account.verifier.charCodeAt(i);
  return difference === 0;
}
export const backupAccount = (data) => {
  const row = data.tables.drafts.find(
    (row) => row.id === `local:${ACCESS_KEY}`,
  );
  return row ? validateAccount(JSON.parse(row.value)) : null;
};

/** Local access lock; it does not claim to encrypt SQLite or replace device security. */
export class OwnerAccess {
  #tail = Promise.resolve();
  constructor(
    ledger,
    session = globalThis.sessionStorage,
    now = () => Date.now(),
  ) {
    this.ledger = ledger;
    this.session = session;
    this.now = now;
  }
  async account() {
    return this.ledger.localSetting(ACCESS_KEY);
  }
  async recoveryAccount(data) {
    return backupAccount(data) || (await this.account());
  }
  async recover(candidate, username, password) {
    const account = await this.recoveryAccount(candidate.data);
    if (account && !(await verifyAccount(account, username, password)))
      throw new Error("Backup username or password is incorrect");
    // Preserve a newly configured owner when the incoming legacy backup has none.
    if (!account) await this.setup(username, password);
    await candidate.restore();
    const restored = await this.account();
    this.session.setItem(ACCESS_KEY, restored.verifier);
  }
  async unlocked() {
    const account = await this.account();
    return Boolean(
      account && this.session.getItem(ACCESS_KEY) === account.verifier,
    );
  }
  lock() {
    this.session.removeItem(ACCESS_KEY);
  }
  async setup(username, password) {
    if (await this.account())
      throw new Error("An owner account already exists. Sign in instead.");
    const account = await createAccount(username, password);
    await this.ledger.saveLocalSetting(ACCESS_KEY, account, true);
    this.session.setItem(ACCESS_KEY, account.verifier);
    return account;
  }
  login(username, password) {
    const work = this.#tail.then(() => this.checkLogin(username, password));
    this.#tail = work.catch(() => {});
    return work;
  }
  async checkLogin(username, password) {
    const account = validateAccount(await this.account());
    const lockout = (await this.ledger.localSetting("access-lockout")) || {
      failures: 0,
      until: 0,
    };
    if (lockout.until > this.now())
      throw new Error("Too many attempts. Wait 30 seconds and try again.");
    if (!(await verifyAccount(account, username, password))) {
      const failures = lockout.failures + 1;
      await this.ledger.saveLocalSetting("access-lockout", {
        failures: failures % 5,
        until: failures >= 5 ? this.now() + 30000 : 0,
      });
      throw new Error("Username or password is incorrect");
    }
    await this.ledger.saveLocalSetting("access-lockout", {
      failures: 0,
      until: 0,
    });
    this.session.setItem(ACCESS_KEY, account.verifier);
  }
}
