````markdown
# API Reference

## Overview

The API is versioned under:

```text
/api/v1/
````

Current API domains:

```text
/api/v1/users/
/api/v1/products/
```

The project uses JSON for normal request and response bodies.

Product image uploads use multipart form data.

JWT access tokens must be sent using:

```http
Authorization: Bearer <access-token>
```

---

# Authentication

## Username and Password Signup

```http
POST /api/v1/users/signup/
```

Creates a user with username/password credentials and returns JWT tokens.

### Authentication

Public.

### Example request

```json
{
  "username": "armin",
  "password": "strong-password",
  "email": "armin@example.com"
}
```

### Success

```text
201 Created
```

The response includes:

* created user data
* access token
* refresh token

Exact response fields follow the current signup output serializers and must remain backward-compatible.

---

## Send Signup OTP

```http
POST /api/v1/users/signup/send-otp/
```

Requests an OTP for phone-based signup.

### Authentication

Public.

### Example request

```json
{
  "phone_number": "09123456789"
}
```

### Example success response

```json
{
  "message": "otp code successfully sent.",
  "expires_in": 120
}
```

### Success

```text
200 OK
```

This endpoint is throttled.

---

## Verify Signup OTP

```http
POST /api/v1/users/signup/verify-otp/
```

Verifies a signup OTP and completes the phone-based signup flow.

### Authentication

Public.

### Example request

```json
{
  "phone_number": "09123456789",
  "otp": "123456"
}
```

### Success

```text
201 Created
```

Invalid, expired, reused, or locked OTP attempts return validation or throttle errors.

---

## Username and Password Login

```http
POST /api/v1/users/login/userpass/
```

Authenticates a user using username and password.

### Authentication

Public.

### Example request

```json
{
  "username": "armin",
  "password": "strong-password"
}
```

### Example success response

```json
{
  "message": "successfully logged in.",
  "tokens": {
    "refresh": "<refresh-token>",
    "access": "<access-token>"
  }
}
```

### Success

```text
200 OK
```

Repeated failed attempts may return:

```text
429 Too Many Requests
```

Authentication failures use a generic response and do not reveal whether the username exists.

---

## Send Login OTP

```http
POST /api/v1/users/login/send-otp/
```

Requests an OTP for phone-based login.

### Authentication

Public.

### Example request

```json
{
  "phone_number": "09123456789"
}
```

### Example success response

```json
{
  "message": "otp code successfully sent.",
  "expires_in": 120
}
```

### Success

```text
200 OK
```

The response is intentionally generic and does not confirm whether the phone number belongs to an account.

---

## Verify Login OTP

```http
POST /api/v1/users/login/verify-otp/
```

Verifies a login OTP and returns JWT tokens.

### Authentication

Public.

### Example request

```json
{
  "phone_number": "09123456789",
  "otp": "123456"
}
```

### Example success response

```json
{
  "message": "successfully logged in.",
  "tokens": {
    "refresh": "<refresh-token>",
    "access": "<access-token>"
  }
}
```

### Success

```text
200 OK
```

---

## Complete Profile

```http
POST /api/v1/users/profile/complete/
```

Completes profile information for the authenticated user.

### Authentication

Required.

### Headers

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

### Success

```text
200 OK
```

Profile completion is informational and does not control login eligibility.

---

## Update Profile

```http
PATCH /api/v1/users/profile/update/
```

Partially updates the authenticated user's profile.

### Authentication

Required.

### Headers

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

### Example request

```json
{
  "first_name": "Armin",
  "last_name": "Example",
  "email": "armin@example.com"
}
```

### Example success response

```json
{
  "message": "your profile is successfully updated.",
  "data": {
    "...": "serialized user fields"
  }
}
```

### Success

```text
200 OK
```

---

## Logout

```http
POST /api/v1/users/logout/
```

Blacklists a refresh token.

### Authentication

Required.

### Example request

```json
{
  "refresh": "<refresh-token>"
}
```

### Example success response

```json
{
  "message": "successfully logged out."
}
```

### Success

```text
200 OK
```

The access token remains usable until its normal expiry.

---

## Send Password Reset OTP

```http
POST /api/v1/users/password-reset/send-otp/
```

Requests an OTP for password reset.

### Authentication

Public.

### Example request

```json
{
  "phone_number": "09123456789"
}
```

### Success

```text
200 OK
```

The response must remain generic and must not reveal whether the account exists.

---

## Verify OTP and Reset Password

```http
POST /api/v1/users/password-reset/verify-and-reset/
```

Verifies the OTP and replaces the account password.

### Authentication

Public.

### Example request

```json
{
  "phone_number": "09123456789",
  "otp": "123456",
  "password": "new-strong-password"
}
```

### Success

```text
200 OK
```

The new password is stored using Django's password hashing system.

---

# Products

## List Products

```http
GET /api/v1/products/
```

Returns the public product catalogue.

### Authentication

Not required.

Authenticated requests are also supported.

### Query behavior

The endpoint supports pagination and may support search, filtering, and ordering according to the current selector and filter configuration.

Configured searchable fields include:

```text
name
sku
description
taste_notes
brand name
category name
```

Configured ordering fields include:

```text
price
created_at
abv
stock
name
volume_ml
```

Default ordering:

```text
-created_at
```

### Success

```text
200 OK
```

### Response

Returns a paginated product list.

Anonymous responses may be served from Redis cache.

---

## Create Product

```http
POST /api/v1/products/
```

Creates a product.

### Authentication

Authenticated administrator/staff access required.

### Headers

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

### Success

```text
201 Created
```

The request body is validated through `ProductWriteInputSerializer`.

Non-admin users receive a permission error.

---

## Retrieve Product

```http
GET /api/v1/products/<product_uuid>/
```

Returns product details by UUID.

### Authentication

Not required.

### Example

```http
GET /api/v1/products/123e4567-e89b-12d3-a456-426614174000/
```

### Success

```text
200 OK
```

Anonymous responses may be served from Redis cache.

Staff users may be able to retrieve inactive products according to the current selector behavior.

---

## Replace Product

```http
PUT /api/v1/products/<product_uuid>/
```

Fully updates a product.

### Authentication

Authenticated administrator/staff access required.

### Success

```text
200 OK
```

---

## Partially Update Product

```http
PATCH /api/v1/products/<product_uuid>/
```

Partially updates a product.

### Authentication

Authenticated administrator/staff access required.

### Example request

```json
{
  "price": "1250000.00",
  "stock": 20
}
```

### Success

```text
200 OK
```

---

## Delete Product

```http
DELETE /api/v1/products/<product_uuid>/
```

Deletes a product according to the current product service behavior.

### Authentication

Authenticated administrator/staff access required.

### Success

```text
204 No Content
```

---

## Upload Product Image

```http
POST /api/v1/products/<product_uuid>/images/upload/
```

Uploads an image for a product.

### Authentication

Authenticated administrator/staff access required.

### Content type

```http
multipart/form-data
```

### Form fields

```text
image
is_primary
display_order
```

### Example

```text
image=<binary file>
is_primary=true
display_order=0
```

### Accepted image formats

```text
JPEG
PNG
WebP
```

The upload validator checks:

* file size
* MIME type
* real image content
* MIME/content consistency
* image dimensions
* corrupt files
* decompression-bomb warnings
* safe filename generation

### Success

```text
201 Created
```

---

## Delete Product Image

```http
DELETE /api/v1/products/images/<image_id>/
```

Deletes a product image by its numeric internal ID.

### Authentication

Authenticated administrator/staff access required.

### Example

```http
DELETE /api/v1/products/images/12/
```

### Success

```text
204 No Content
```

---

# Permissions Summary

| Endpoint group               | Public | Authenticated user | Admin/staff |
| ---------------------------- | -----: | -----------------: | ----------: |
| Signup and login             |    Yes |                Yes |         Yes |
| Password reset               |    Yes |                Yes |         Yes |
| Profile operations           |     No |                Yes |         Yes |
| Logout                       |     No |                Yes |         Yes |
| Product list/detail          |    Yes |                Yes |         Yes |
| Product create/update/delete |     No |                 No |         Yes |
| Product image upload/delete  |     No |                 No |         Yes |

---

# Common Status Codes

```text
200 OK
201 Created
204 No Content
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
429 Too Many Requests
503 Service Unavailable
```

## `400 Bad Request`

Used for invalid request data, invalid OTP values, validation failures, and identity conflicts.

## `401 Unauthorized`

Used when authentication credentials are missing or invalid.

## `403 Forbidden`

Used when an authenticated user does not have sufficient permission.

## `404 Not Found`

Used when the requested resource does not exist or is not visible to the requester.

## `429 Too Many Requests`

Used for throttling and temporary authentication lockouts.

## `503 Service Unavailable`

Used when authentication protection cannot safely access the security cache.

---

# Pagination

Product lists use the project's custom pagination class.

The configured default page size is:

```text
12
```

A typical response may contain:

```json
{
  "count": 25,
  "next": "http://example.com/api/v1/products/?page=2",
  "previous": null,
  "results": []
}
```

The exact pagination field names follow `CustomPagination`.

---

# API Stability

The following should not change without an explicit compatibility decision:

* existing routes
* HTTP methods
* JWT token response structure
* authentication response structure
* public versus protected endpoint behavior
* identifier types such as product UUID and image integer ID

When new domains are added, they should use the same `/api/v1/` version prefix.

