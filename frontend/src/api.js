const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request(path, options = {}) {
  const { body, isForm = false, headers = {}, ...rest } = options;
  const finalOptions = {
    credentials: "include",
    ...rest,
    headers: {
      ...headers
    }
  };

  if (body !== undefined) {
    if (isForm) {
      finalOptions.body = body;
    } else {
      finalOptions.headers["Content-Type"] = "application/json";
      finalOptions.body = JSON.stringify(body);
    }
  }

  const response = await fetch(`${API_BASE}${path}`, finalOptions);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "string"
        ? payload
        : payload.message || payload.Message || payload.detail || "Request failed";
    throw new Error(message);
  }

  return payload;
}

export const api = {
  register: (data) =>
    request("/authentication/register", {
      method: "POST",
      body: data
    }),
  login: (data) =>
    request("/authentication/login", {
      method: "POST",
      body: data
    }),
  me: () =>
    request("/authentication/me", {
      method: "GET"
    }),
  logout: () =>
    request("/authentication/logout", {
      method: "POST"
    }),
  loadExcel: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/products/load-excel", {
      method: "POST",
      body: formData,
      isForm: true
    });
  },
  dashboard: () =>
    request("/products/dashboard", {
      method: "GET"
    }),
  inventory: () =>
    request("/products/inventory", {
      method: "GET"
    }),
  products: () =>
    request("/products/", {
      method: "GET"
    }),
  createProduct: (data) =>
    request("/products/", {
      method: "POST",
      body: data
    }),
  updateProduct: (id, data) =>
    request(`/products/${id}`, {
      method: "PUT",
      body: data
    }),
  deleteProduct: (id) =>
    request(`/products/${id}`, {
      method: "DELETE"
    }),
  adminExcelSnapshot: () =>
    request("/products/admin/excel-snapshot", {
      method: "GET"
    }),
  createStockEntry: (data) =>
    request("/products/admin/stock-entry", {
      method: "POST",
      body: data
    })
};
