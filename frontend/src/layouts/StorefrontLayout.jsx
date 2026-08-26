import { Outlet } from "react-router-dom";

import FooterNotice from "../components/FooterNotice";
import Header from "../components/Header";

export default function StorefrontLayout() {
  return (
    <div className="app-shell">
      <Header />
      <main id="main-content" className="site-main">
        <Outlet />
      </main>
      <FooterNotice />
    </div>
  );
}
