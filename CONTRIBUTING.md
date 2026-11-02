# Contributing to BillFlow

Thank you for your interest in contributing to BillFlow. We welcome bug reports, feature suggestions, documentation enhancements, and code contributions.

---

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/prabhas9192/Sales-Billing-Software.git
   cd Sales-Billing-Software
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the automated test suite:
   ```bash
   python -m unittest discover -s tests -v
   ```

---

## Code Guidelines

- **Zero Emojis**: In accordance with project design standards, user interfaces, logs, and comments must not contain Unicode emojis.
- **Resource Management**: All SQLite connections must use proper context managers (`with get_conn():` or `contextlib.closing`) to prevent file descriptor leaks.
- **Separation of Concerns**: Keep business logic decoupled from UI views.

---

## Submitting Pull Requests

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Commit your changes: `git commit -m "feat: description of change"`
3. Push to your fork: `git push origin feature/your-feature-name`
4. Open a Pull Request against the `main` branch.
