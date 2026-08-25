export function CatalogueSkeleton() {
  return (
    <div className="product-grid skeleton-grid" role="status" aria-label="Loading fragrances">
      <span className="sr-only">Loading fragrances</span>
      {Array.from({ length: 6 }, (_, index) => (
        <div className="product-skeleton" key={index} aria-hidden="true">
          <div className="skeleton-media" />
          <div className="skeleton-line skeleton-line-short" />
          <div className="skeleton-line" />
          <div className="skeleton-line skeleton-line-price" />
        </div>
      ))}
    </div>
  );
}
