import { useMemo, useState } from "react";

import { imageSource } from "../utils/images";

function orderedImages(images) {
  return [...(images || [])].sort((left, right) => {
    if (left.is_primary !== right.is_primary) return left.is_primary ? -1 : 1;
    return left.display_order - right.display_order || left.id - right.id;
  });
}

export default function ProductGallery({ images, productName, brandName }) {
  const ordered = useMemo(() => orderedImages(images), [images]);
  const [selectedId, setSelectedId] = useState(ordered[0]?.id ?? null);
  const [failedIds, setFailedIds] = useState(new Set());
  const selected = ordered.find((image) => image.id === selectedId) || ordered[0];
  const selectedIndex = Math.max(ordered.indexOf(selected), 0);
  const selectedFailed = selected ? failedIds.has(selected.id) : false;

  function markFailed(id) {
    setFailedIds((current) => new Set([...current, id]));
  }

  return (
    <section className="product-gallery" aria-label={`${productName} image gallery`}>
      <div className="product-gallery-main">
        {selected && !selectedFailed ? (
          <img
            src={imageSource(selected)}
            alt={`${productName} by ${brandName || "Luxury Perfume"} — image ${selectedIndex + 1}`}
            onError={() => markFailed(selected.id)}
          />
        ) : (
          <span className="image-fallback" aria-label={`No image available for ${productName}`}>Luxury Perfume</span>
        )}
      </div>
      {ordered.length > 1 ? (
        <div className="product-thumbnails" aria-label="Choose product image">
          {ordered.map((image, index) => (
            <button
              key={image.id}
              type="button"
              className={image.id === selected?.id ? "is-selected" : ""}
              aria-pressed={image.id === selected?.id}
              aria-label={`View ${productName} image ${index + 1}`}
              onClick={() => setSelectedId(image.id)}
            >
              {failedIds.has(image.id) ? (
                <span aria-hidden="true">LP</span>
              ) : (
                <img src={imageSource(image, true)} alt="" onError={() => markFailed(image.id)} />
              )}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
