import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { listProducts } from "../api/products";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import { CatalogueSkeleton } from "../components/LoadingSkeletons";
import Pagination from "../components/Pagination";
import ProductCard from "../components/ProductCard";
import ProductFilters from "../components/ProductFilters";
import useDocumentTitle from "../hooks/useDocumentTitle";

export default function CataloguePage() {
  useDocumentTitle("Perfume collection");
  const [searchParams] = useSearchParams();
  const parameters = useMemo(() => Object.fromEntries(searchParams.entries()), [searchParams]);
  const requestParameters = JSON.stringify(parameters);
  const [state, setState] = useState({ data: null, error: null, request: null });
  const [attempt, setAttempt] = useState(0);
  const request = `${requestParameters}:${attempt}`;
  const loading = state.request !== request;
  const error = loading ? null : state.error;

  const load = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    listProducts(parameters, controller.signal)
      .then((data) => setState({ data, error: null, request }))
      .catch((error) => {
        if (error.name !== "AbortError") setState((current) => ({ ...current, error, request }));
      });
    return () => controller.abort();
  }, [parameters, request]);

  return (
    <div className="catalogue-page page-frame">
      <header className="catalogue-masthead">
        <div>
          <p className="eyebrow">The fragrance collection</p>
          <h1 id="catalogue-title">Find your signature.</h1>
        </div>
        <div className="sillage-line" aria-hidden="true" />
        <p className="catalogue-count" aria-live="polite">
          {state.data ? `${state.data.count} fragrances` : "Curating the collection"}
        </p>
      </header>
      <ProductFilters />
      <section aria-labelledby="catalogue-title" className={loading && state.data ? "is-refreshing" : ""}>
        {loading && !state.data ? <CatalogueSkeleton /> : null}
        {error ? (
          <ErrorState
            title="The collection could not be loaded"
            message="Check your connection, then try the collection again."
            onRetry={load}
          />
        ) : null}
        {!loading && !error && state.data?.results.length === 0 ? (
          <EmptyState title="No fragrances found">
            Try a different search or remove one of the filters.
          </EmptyState>
        ) : null}
        {state.data?.results.length ? (
          <div className="product-grid">
            {state.data.results.map((product) => <ProductCard key={product.uuid} product={product} />)}
          </div>
        ) : null}
      </section>
      {state.data ? <Pagination currentPage={state.data.current_page} totalPages={state.data.total_pages} /> : null}
    </div>
  );
}
