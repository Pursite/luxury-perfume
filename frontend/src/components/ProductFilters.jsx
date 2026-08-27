import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

const FILTERS = [
  ["target_audience", "Audience", [["", "All audiences"], ["men", "Men"], ["women", "Women"], ["unisex", "Unisex"]]],
  ["concentration", "Concentration", [["", "All concentrations"], ["parfum", "Parfum"], ["eau_de_parfum", "Eau de parfum"], ["eau_de_toilette", "Eau de toilette"]]],
  ["fragrance_family", "Family", [["", "All families"], ["amber", "Amber"], ["aromatic", "Aromatic"], ["citrus", "Citrus"], ["floral", "Floral"], ["woody", "Woody"]]],
];

export default function ProductFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const committedSearch = searchParams.get("search") || "";
  const [searchState, setSearchState] = useState({
    committed: committedSearch,
    value: committedSearch,
  });
  const [isComposing, setIsComposing] = useState(false);
  const searchRef = useRef(null);

  if (searchState.committed !== committedSearch) {
    setSearchState({ committed: committedSearch, value: committedSearch });
  }

  const search = searchState.value;

  function setSearch(value) {
    setSearchState({ committed: committedSearch, value });
  }

  useEffect(() => {
    if (isComposing) return undefined;
    const timer = window.setTimeout(() => {
      const current = searchParams.get("search") || "";
      if (current === search) return;
      const next = new URLSearchParams(searchParams);
      if (search) next.set("search", search);
      else next.delete("search");
      next.delete("page");
      setSearchParams(next, { replace: true });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [isComposing, search, searchParams, setSearchParams]);

  function setFilter(name, value) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    setSearchParams(next);
  }

  function clearSearch() {
    setSearch("");
    const next = new URLSearchParams(searchParams);
    next.delete("search");
    next.delete("page");
    setSearchParams(next, { replace: true });
    searchRef.current?.focus();
  }

  return (
    <form className="catalogue-filters" role="search" noValidate onSubmit={(event) => event.preventDefault()}>
      <div className="search-field">
        <label htmlFor="catalogue-search">Search fragrances</label>
        <div className="search-control">
          <input
            ref={searchRef}
            id="catalogue-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={(event) => {
              setIsComposing(false);
              setSearch(event.currentTarget.value);
            }}
          />
          {search ? (
            <button type="button" className="search-clear" onClick={clearSearch} aria-label="Clear search">
              ×
            </button>
          ) : null}
        </div>
      </div>
      <div className="filter-band">
        <div className="filter-band-heading">
          <span className="filter-band-kicker">Refine the collection</span>
          <span className="filter-band-note">Five quiet filters</span>
        </div>
        <div className="filter-row">
        {FILTERS.map(([name, title, options]) => (
          <label key={name}>
            <span>{title}</span>
            <select value={searchParams.get(name) || ""} onChange={(event) => setFilter(name, event.target.value)}>
              {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        ))}
        <label>
          <span>Availability</span>
          <select value={searchParams.get("in_stock") || ""} onChange={(event) => setFilter("in_stock", event.target.value)}>
            <option value="">All products</option>
            <option value="true">In stock</option>
          </select>
        </label>
        <label>
          <span>Order</span>
          <select value={searchParams.get("ordering") || "-created_at"} onChange={(event) => setFilter("ordering", event.target.value)}>
            <option value="-created_at">Newest</option>
            <option value="name">Name A–Z</option>
            <option value="-name">Name Z–A</option>
          </select>
        </label>
        </div>
      </div>
    </form>
  );
}
