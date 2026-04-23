# Credential Vault — Custom-AlgoPure

Credentials are stored in **Windows Credential Manager** (built into Windows — no extra software).  
The Python bot reads them via the `keyring` library instead of plaintext `.env` files.

This means `.env` holds only non-sensitive config (symbol, timeframe, risk settings).  
Passwords and login tokens never touch disk in plaintext.

---

## 1. Install keyring

```bash
pip install keyring
```

---

## 2. Store credentials (one-time setup)

Run these commands once. Windows stores them in Credential Manager, protected by your Windows login.

### AlgoPure profile
```bash
python -c "import keyring; keyring.set_password('mt5', 'algopure_login',    'YOUR_ACCOUNT')"
python -c "import keyring; keyring.set_password('mt5', 'algopure_password', 'YOUR_PASSWORD')"
python -c "import keyring; keyring.set_password('mt5', 'algopure_server',   'YOUR_SERVER')"
```

### MetaQuotes Demo (shared vault entry)
```bash
python -c "import keyring; keyring.set_password('mt5', 'metaquotes_login',    'YOUR_ACCOUNT')"
python -c "import keyring; keyring.set_password('mt5', 'metaquotes_password', 'YOUR_PASSWORD')"
python -c "import keyring; keyring.set_password('mt5', 'metaquotes_server',   'MetaQuotes-Demo')"
```

> **Tip:** Open **Windows Credential Manager** (Start → search "Credential Manager" → Windows Credentials tab)  
> to view, edit, or delete any stored entry via the GUI.

---

## 3. Verify stored credentials

```bash
python -c "
import keyring
for key in ['algopure_login', 'algopure_server', 'metaquotes_login']:
    val = keyring.get_password('mt5', key)
    print(f'{key:30s}: {\"SET\" if val else \"NOT SET\"}')"
```

---

## 4. Delete a credential

```bash
python -c "import keyring; keyring.delete_password('mt5', 'algopure_password')"
```

---

## Credential inventory

| Service | Key name               | What it stores            |
|---------|------------------------|---------------------------|
| `mt5`   | `algopure_login`       | AlgoPure account number   |
| `mt5`   | `algopure_password`    | AlgoPure password         |
| `mt5`   | `algopure_server`      | AlgoPure server name      |
| `mt5`   | `metaquotes_login`     | MetaQuotes account number |
| `mt5`   | `metaquotes_password`  | MetaQuotes password       |
| `mt5`   | `metaquotes_server`    | MetaQuotes server name    |
| `mt5`   | `blackbull_login`      | BlackBull account number  |
| `mt5`   | `blackbull_password`   | BlackBull password        |
| `mt5`   | `blackbull_server`     | BlackBull server name     |
