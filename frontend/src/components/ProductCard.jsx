import { useState } from "react";
import { Link } from "react-router-dom";

import { imageSource } from "../utils/images";
import Availability from "./Availability";
import Price from "./Price";

function label(value) {
  return value ? value.replaceAll("_", " ") : "";
}

export default function ProductCard({ product }) {
  const [imageFailed, setImageFailed] = useState(false);
  const source = imageSource(product.primary_image, true);

  return (
    <article className="product-card">
      <Link className="product-card-link" to={`/products/${product.slug}`}>
        <div className="product-card-media">
          {source && !imageFailed ? (
            <img
              src={source}
              alt={`${product.name} by ${product.brand?.name || "EXON+"}`}
              loading="lazy"
              onError={() => setImageFailed(true)}
            />
          ) : (
            <span className="image-fallback" aria-label={`No image available for ${product.name}`}>
              EXON+
            </span>
          )}
          {product.is_featured ? <span className="featured-mark">Featured</span> : null}
        </div>
        <div className="product-card-body">
          <p className="product-brand">{product.brand?.name || "Independent perfume"}</p>
          <h2>{product.name}</h2>
          <p className="product-facts">
            {product.volume_ml ? `${product.volume_ml} ml` : null}
            {product.volume_ml && product.concentration ? <span aria-hidden="true"> · </span> : null}
            {label(product.concentration)}
          </p>
          <Price
            price={product.price}
            finalPrice={product.final_price}
            discountPrice={product.discount_price}
          />
          <Availability stock={product.stock} />
        </div>
      </Link>
    </article>
  );
}
