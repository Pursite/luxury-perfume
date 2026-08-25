function Icon({ children }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export function ProductsIcon() {
  return (
    <Icon>
      <path d="M8 3.75h8M9.25 3.75v3.1l-3.5 4.05v7.85c0 .83.67 1.5 1.5 1.5h9.5c.83 0 1.5-.67 1.5-1.5V10.9l-3.5-4.05v-3.1" />
      <path d="M7.25 12.25h9.5" />
    </Icon>
  );
}

export function CartIcon() {
  return (
    <Icon>
      <path d="M3.75 5.25h2l1.35 9.1c.1.67.67 1.15 1.35 1.15h8.8c.62 0 1.17-.42 1.32-1.02l1.18-5.23H6.35" />
      <circle cx="9" cy="19" r="1.25" />
      <circle cx="17" cy="19" r="1.25" />
    </Icon>
  );
}

export function AccountIcon() {
  return (
    <Icon>
      <circle cx="12" cy="8" r="3.25" />
      <path d="M5.5 20c.55-4 2.72-6 6.5-6s5.95 2 6.5 6" />
    </Icon>
  );
}
