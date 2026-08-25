import { backendUrl } from "../api/client";

export function imageSource(image, preferThumbnail = false) {
  if (!image) return null;
  const source = preferThumbnail ? image.thumbnail || image.image : image.image || image.thumbnail;
  return source ? backendUrl(source) : null;
}
