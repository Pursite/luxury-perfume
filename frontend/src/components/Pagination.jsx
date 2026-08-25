import { useSearchParams } from "react-router-dom";

export default function Pagination({ currentPage, totalPages }) {
  const [searchParams, setSearchParams] = useSearchParams();
  if (totalPages <= 1) return null;

  function goTo(page) {
    const next = new URLSearchParams(searchParams);
    if (page === 1) next.delete("page");
    else next.set("page", String(page));
    setSearchParams(next);
    window.scrollTo?.({ top: 0, behavior: "smooth" });
  }

  return (
    <nav className="pagination" aria-label="Product catalogue pages">
      <button type="button" onClick={() => goTo(currentPage - 1)} disabled={currentPage <= 1}>
        Previous
      </button>
      <span aria-live="polite">
        Page {currentPage} of {totalPages}
      </span>
      <button type="button" onClick={() => goTo(currentPage + 1)} disabled={currentPage >= totalPages}>
        Next
      </button>
    </nav>
  );
}
