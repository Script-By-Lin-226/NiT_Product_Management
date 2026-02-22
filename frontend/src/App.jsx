import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { api } from "./api";

const USER_STORAGE_PREFIX = "nitpm:user-data:v1";

function getUserStorageKey(user) {
  const userIdentifier = user?.id ?? user?.email;
  if (!userIdentifier) {
    return null;
  }
  return `${USER_STORAGE_PREFIX}:${String(userIdentifier)}`;
}

function readUserSnapshot(user) {
  const storageKey = getUserStorageKey(user);
  if (!storageKey) {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(storageKey);
    return rawValue ? JSON.parse(rawValue) : null;
  } catch {
    return null;
  }
}

function writeUserSnapshot(user, snapshot) {
  const storageKey = getUserStorageKey(user);
  if (!storageKey) {
    return;
  }

  try {
    window.localStorage.setItem(storageKey, JSON.stringify(snapshot));
  } catch {
    // Ignore storage issues (private mode, quota, disabled storage).
  }
}

function toDatetimeLocalValue(date = new Date()) {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 16);
}

const BOY_SHIRT_SIZES = ["M", "L", "XL", "2XL", "3XL"];
const GIRL_SHIRT_SIZES = ["S", "M", "L", "XL", "2XL"];
const BOY_PANT_SIZES = ["28", "30", "32", "34", "36", "38"];
const GIRL_BOTTOM_SIZES = ["24", "26", "28", "30", "32"];

function createDefaultNewProductForm() {
  return {
    product_name: ""
  };
}

function getUniformItemOptions(gender) {
  return ["shirt", "pant"];
}

function getUniformSizeOptions(gender, item) {
  if (item === "shirt") {
    return gender === "girl" ? GIRL_SHIRT_SIZES : BOY_SHIRT_SIZES;
  }
  if (gender === "girl") {
    return GIRL_BOTTOM_SIZES;
  }
  return BOY_PANT_SIZES;
}

function normalizeUniformForm(form) {
  const candidate = form && typeof form === "object" ? form : {};
  const gender = candidate.gender === "girl" ? "girl" : "boy";
  const validItems = getUniformItemOptions(gender);
  const item = validItems.includes(candidate.item) ? candidate.item : validItems[0];
  const sleeve = candidate.sleeve === "long" ? "long" : "short";
  const sizeOptions = getUniformSizeOptions(gender, item);
  const size = sizeOptions.includes(candidate.size) ? candidate.size : sizeOptions[0];
  return { gender, item, sleeve, size };
}

function buildUniformProductName(form) {
  const normalized = normalizeUniformForm(form);
  const genderLabel = normalized.gender === "girl" ? "Girl" : "Boy";
  const itemLabel =
    normalized.item === "shirt"
      ? `Shirt (${normalized.sleeve === "long" ? "Long" : "Short"})`
      : "Pant";

  return `Uniform - ${itemLabel} - ${genderLabel} - Size ${normalized.size}`;
}

function parseUniformProductName(productName) {
  const value = typeof productName === "string" ? productName.trim() : "";
  const match = value.match(
    /^Uniform\s*-\s*(Shirt\s*\((Short|Long)\)|Skirt|Pant)\s*-\s*(Boy|Girl)\s*-\s*Size\s*([A-Za-z0-9]+)\s*$/i
  );
  if (!match) {
    return null;
  }

  const rawItem = (match[1] || "").toLowerCase();
  const rawSleeve = (match[2] || "").toLowerCase();
  const gender = (match[3] || "").toLowerCase() === "girl" ? "girl" : "boy";
  const size = (match[4] || "").toUpperCase();

  if (rawItem.startsWith("shirt")) {
    return {
      gender,
      item: "shirt",
      sleeve: rawSleeve === "long" ? "long" : "short",
      size
    };
  }

  return {
    gender,
    item: "pant",
    sleeve: "",
    size
  };
}

function createDefaultStockEntryForm() {
  return {
    stock_entry_type: "uniform",
    product_name: "",
    other_product_name: "",
    uniform_gender: "",
    uniform_item: "",
    uniform_sleeve: "",
    uniform_size: "",
    movement: "in",
    quantity: "1",
    entry_date: toDatetimeLocalValue(),
    given_to: "",
    department: ""
  };
}

function App() {
  const [authMode, setAuthMode] = useState("login");
  const [activePage, setActivePage] = useState("dashboard");
  const [authForm, setAuthForm] = useState({
    username: "",
    email: "",
    password: ""
  });
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const [dashboard, setDashboard] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [dashboardBusy, setDashboardBusy] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [adminMessage, setAdminMessage] = useState("");
  const [crudBusy, setCrudBusy] = useState(false);
  const [adminProducts, setAdminProducts] = useState([]);
  const [adminDrafts, setAdminDrafts] = useState({});
  const [newProductForm, setNewProductForm] = useState(createDefaultNewProductForm());
  const [excelSnapshot, setExcelSnapshot] = useState({
    file_path: "app/Services/data.xlsx",
    products: [],
    items: [],
    summary: {
      product_count: 0,
      total_stock_balance: 0
    }
  });
  const [stockEntryForm, setStockEntryForm] = useState(createDefaultStockEntryForm());
  const [stockEntryBusy, setStockEntryBusy] = useState(false);
  const [error, setError] = useState("");
  const [recentLogFilters, setRecentLogFilters] = useState({
    category: "all",
    date_from: "",
    date_to: ""
  });
  const restoredStorageKeyRef = useRef(null);

  const isAdmin = Boolean(currentUser?.is_admin);

  const resetMessages = () => {
    setError("");
    setAuthMessage("");
    setUploadMessage("");
    setAdminMessage("");
  };

  const loadAdminProducts = useCallback(async () => {
    const productsPayload = await api.products();
    setAdminProducts(productsPayload);
    setAdminDrafts(
      productsPayload.reduce((accumulator, item) => {
        accumulator[item.id] = {
          product_name: item.product_name,
          quantity: String(item.quantity)
        };
        return accumulator;
      }, {})
    );
  }, []);

  const loadExcelSnapshot = useCallback(async () => {
    const snapshotPayload = await api.adminExcelSnapshot();
    setExcelSnapshot(snapshotPayload);
    setStockEntryForm((previous) => {
      const hasCurrentProduct = snapshotPayload.products?.includes(previous.product_name);
      const selectedProductName = hasCurrentProduct
        ? previous.product_name
        : "";
      const parsedSelection = parseUniformProductName(selectedProductName);
      return {
        ...previous,
        stock_entry_type: parsedSelection ? "uniform" : selectedProductName ? "other" : previous.stock_entry_type,
        product_name: selectedProductName,
        other_product_name: parsedSelection ? "" : selectedProductName,
        uniform_gender: parsedSelection?.gender || "",
        uniform_item: parsedSelection?.item || "",
        uniform_sleeve: parsedSelection?.sleeve || "",
        uniform_size: parsedSelection?.size || ""
      };
    });
  }, []);

  const refreshDashboard = useCallback(
    async (silent = false) => {
      setDashboardBusy(true);
      if (!silent) {
        setError("");
      }

      try {
        const [dashboardPayload, inventoryPayload, mePayload] = await Promise.all([
          api.dashboard(),
          api.inventory(),
          api.me()
        ]);
        setDashboard(dashboardPayload);
        setInventory(inventoryPayload.items || []);
        setCurrentUser(mePayload);
        setIsAuthenticated(true);

        if (mePayload?.is_admin) {
          await loadAdminProducts();
          await loadExcelSnapshot();
        } else {
          setAdminProducts([]);
          setAdminDrafts({});
          setExcelSnapshot({
            file_path: "app/Services/data.xlsx",
            products: [],
            items: [],
            summary: {
              product_count: 0,
              total_stock_balance: 0
            }
          });
        }
      } catch (refreshError) {
        setDashboard(null);
        setInventory([]);
        setCurrentUser(null);
        setIsAuthenticated(false);
        setAdminProducts([]);
        setAdminDrafts({});
        setExcelSnapshot({
          file_path: "app/Services/data.xlsx",
          products: [],
          items: [],
          summary: {
            product_count: 0,
            total_stock_balance: 0
          }
        });
        if (!silent) {
          setError(refreshError.message);
        }
      } finally {
        setDashboardBusy(false);
      }
    },
    [loadAdminProducts, loadExcelSnapshot]
  );

  useEffect(() => {
    refreshDashboard(true);
  }, [refreshDashboard]);

  useEffect(() => {
    if (activePage === "admin" && isAuthenticated && isAdmin) {
      loadExcelSnapshot().catch(() => {
        // Error already surfaced by API call contexts when needed.
      });
    }
  }, [activePage, isAdmin, isAuthenticated, loadExcelSnapshot]);

  useEffect(() => {
    if (!isAuthenticated || !currentUser) {
      restoredStorageKeyRef.current = null;
      return;
    }

    const storageKey = getUserStorageKey(currentUser);
    if (!storageKey || restoredStorageKeyRef.current === storageKey) {
      return;
    }

    const snapshot = readUserSnapshot(currentUser);
    if (snapshot) {
      if (!dashboard && snapshot.dashboard) {
        setDashboard(snapshot.dashboard);
      }
      if ((!inventory || inventory.length === 0) && Array.isArray(snapshot.inventory)) {
        setInventory(snapshot.inventory);
      }
      if (
        currentUser?.is_admin &&
        (!adminProducts || adminProducts.length === 0) &&
        Array.isArray(snapshot.adminProducts)
      ) {
        setAdminProducts(snapshot.adminProducts);
      }
      if (
        currentUser?.is_admin &&
        Object.keys(adminDrafts || {}).length === 0 &&
        snapshot.adminDrafts &&
        typeof snapshot.adminDrafts === "object"
      ) {
        setAdminDrafts(snapshot.adminDrafts);
      }
      if (
        currentUser?.is_admin &&
        snapshot.newProductForm &&
        typeof snapshot.newProductForm === "object"
      ) {
        setNewProductForm((previous) => ({
          ...previous,
          ...snapshot.newProductForm
        }));
      }
      if (
        currentUser?.is_admin &&
        snapshot.excelSnapshot &&
        typeof snapshot.excelSnapshot === "object"
      ) {
        setExcelSnapshot(snapshot.excelSnapshot);
      }
      if (
        currentUser?.is_admin &&
        snapshot.stockEntryForm &&
        typeof snapshot.stockEntryForm === "object"
      ) {
        setStockEntryForm((previous) => ({
          ...previous,
          ...snapshot.stockEntryForm
        }));
      }
    }

    restoredStorageKeyRef.current = storageKey;
  }, [adminDrafts, adminProducts, currentUser, dashboard, inventory, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated || !currentUser) {
      return;
    }

    writeUserSnapshot(currentUser, {
      dashboard,
      inventory,
      adminProducts: isAdmin ? adminProducts : [],
      adminDrafts: isAdmin ? adminDrafts : {},
      newProductForm: isAdmin ? newProductForm : null,
      excelSnapshot: isAdmin ? excelSnapshot : null,
      stockEntryForm: isAdmin ? stockEntryForm : null,
      savedAt: new Date().toISOString()
    });
  }, [
    adminDrafts,
    adminProducts,
    currentUser,
    dashboard,
    excelSnapshot,
    inventory,
    isAdmin,
    isAuthenticated,
    newProductForm,
    stockEntryForm
  ]);

  const handleAuthChange = (event) => {
    const { name, value } = event.target;
    setAuthForm((previous) => ({ ...previous, [name]: value }));
  };

  const switchMode = (mode) => {
    setAuthMode(mode);
    setAuthMessage("");
    setError("");
  };

  const handleAuthSubmit = async (event) => {
    event.preventDefault();
    resetMessages();
    setAuthBusy(true);

    try {
      if (authMode === "register") {
        const registerPayload = await api.register({
          username: authForm.username,
          email: authForm.email,
          password: authForm.password
        });
        setAuthMessage(registerPayload.message || "Registration successful");
        setAuthMode("login");
      } else {
        const loginPayload = await api.login({
          email: authForm.email,
          password: authForm.password
        });
        setAuthMessage(loginPayload.Message || "Login successful");
        await refreshDashboard();
      }
    } catch (authError) {
      setError(authError.message);
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLogout = async () => {
    resetMessages();
    try {
      await api.logout();
    } catch (logoutError) {
      setError(logoutError.message);
    } finally {
      setActivePage("dashboard");
      setIsAuthenticated(false);
      setCurrentUser(null);
      setDashboard(null);
      setInventory([]);
      setAdminProducts([]);
      setAdminDrafts({});
      setNewProductForm(createDefaultNewProductForm());
      setExcelSnapshot({
        file_path: "app/Services/data.xlsx",
        products: [],
        items: [],
        summary: {
          product_count: 0,
          total_stock_balance: 0
        }
      });
      setStockEntryForm(createDefaultStockEntryForm());
    }
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    resetMessages();

    if (!selectedFile) {
      setError("Select an Excel file first.");
      return;
    }

    if (!isAdmin) {
      setError("Admin access required.");
      return;
    }

    setUploadBusy(true);
    try {
      const uploadPayload = await api.loadExcel(selectedFile);
      const summary = uploadPayload.summary || {};
      setUploadMessage(
        `${uploadPayload.message}. Created: ${summary.created || 0}, Updated: ${summary.updated || 0}, Unchanged: ${summary.unchanged || 0}`
      );
      await refreshDashboard();
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploadBusy(false);
    }
  };

  const handleNewProductChange = (event) => {
    const { name, value } = event.target;
    setNewProductForm((previous) => ({ ...previous, [name]: value }));
  };

  const handleStockEntryChange = (event) => {
    const { name, value } = event.target;
    if (name === "stock_entry_type") {
      setStockEntryForm((previous) => {
        const next = { ...previous, stock_entry_type: value };
        if (value === "uniform") {
          next.other_product_name = "";
          next.product_name = "";
          return next;
        }

        next.uniform_gender = "";
        next.uniform_item = "";
        next.uniform_sleeve = "";
        next.uniform_size = "";
        next.product_name = next.other_product_name || "";
        return next;
      });
      return;
    }

    if (name === "other_product_name") {
      setStockEntryForm((previous) => ({
        ...previous,
        other_product_name: value,
        product_name: value
      }));
      return;
    }

    if (name.startsWith("uniform_")) {
      setStockEntryForm((previous) => {
        const next = {
          ...previous,
          stock_entry_type: "uniform",
          other_product_name: "",
          [name]: value
        };

        if (name === "uniform_gender") {
          if (!value) {
            next.uniform_item = "";
            next.uniform_sleeve = "";
            next.uniform_size = "";
          } else {
            const validItems = getUniformItemOptions(value);
            if (!validItems.includes(next.uniform_item)) {
              next.uniform_item = "";
            }
            if (next.uniform_item !== "shirt") {
              next.uniform_sleeve = "";
            }
            const validSizes = next.uniform_item
              ? getUniformSizeOptions(value, next.uniform_item)
              : [];
            if (!validSizes.includes(next.uniform_size)) {
              next.uniform_size = "";
            }
          }
        }

        if (name === "uniform_item") {
          if (value !== "shirt") {
            next.uniform_sleeve = "";
          } else if (!next.uniform_sleeve) {
            next.uniform_sleeve = "short";
          }
          const validSizes =
            next.uniform_gender && value
              ? getUniformSizeOptions(next.uniform_gender, value)
              : [];
          if (!validSizes.includes(next.uniform_size)) {
            next.uniform_size = "";
          }
        }

        const hasRequiredSelection =
          next.uniform_gender &&
          next.uniform_item &&
          next.uniform_size &&
          (next.uniform_item !== "shirt" || next.uniform_sleeve);

        if (!hasRequiredSelection) {
          next.product_name = "";
          return next;
        }

        const candidateProductName = buildUniformProductName({
          gender: next.uniform_gender,
          item: next.uniform_item,
          sleeve: next.uniform_item === "shirt" ? next.uniform_sleeve : "short",
          size: next.uniform_size
        });
        const availableProductNames = new Set(
          (excelSnapshot?.items || []).map((item) => item.product_name)
        );
        next.product_name = availableProductNames.has(candidateProductName)
          ? candidateProductName
          : "";
        return next;
      });
      return;
    }

    setStockEntryForm((previous) => ({ ...previous, [name]: value }));
  };

  const handleStockEntrySubmit = async (event) => {
    event.preventDefault();
    resetMessages();

    if (!isAuthenticated || !isAdmin) {
      setError("Admin access required.");
      return;
    }

    if (!stockEntryForm.product_name) {
      setError("Select a product from the dropdowns.");
      return;
    }

    const quantityValue = Number(stockEntryForm.quantity);
    if (!Number.isInteger(quantityValue) || quantityValue <= 0) {
      setError("Quantity must be a positive integer.");
      return;
    }
    const givenToValue = stockEntryForm.given_to.trim();
    const departmentValue = stockEntryForm.department.trim();
    if (stockEntryForm.movement === "out" && (!givenToValue || !departmentValue)) {
      setError("For Out entries, both Given To and Department are required.");
      return;
    }

    setStockEntryBusy(true);
    try {
      const payload = {
        product_name: stockEntryForm.product_name,
        movement: stockEntryForm.movement,
        quantity: quantityValue,
        entry_date: stockEntryForm.entry_date
          ? new Date(stockEntryForm.entry_date).toISOString()
          : null,
        given_to: givenToValue || null,
        department: departmentValue || null
      };
      const response = await api.createStockEntry(payload);
      const balanceValue = response?.entry?.balance;
      const totalStockValue = response?.summary?.total_stock_balance;
      setAdminMessage(
        `${response.message} Product balance: ${balanceValue ?? "N/A"}, Total stock balance: ${totalStockValue ?? "N/A"}`
      );
      setStockEntryForm((previous) => ({
        ...previous,
        quantity: "1",
        entry_date: toDatetimeLocalValue(),
        given_to: "",
        department: ""
      }));
      await Promise.all([refreshDashboard(true), loadExcelSnapshot()]);
    } catch (entryError) {
      setError(entryError.message);
    } finally {
      setStockEntryBusy(false);
    }
  };

  const handleCreateProduct = async (event) => {
    event.preventDefault();
    resetMessages();

    if (!isAdmin) {
      setError("Admin access required.");
      return;
    }

    const productName = (newProductForm.product_name || "").trim();
    if (!productName) {
      setError("Product name is required.");
      return;
    }

    setCrudBusy(true);
    try {
      await api.createProduct({
        product_name: productName,
        quantity: 0
      });
      setAdminMessage(`Product created: ${productName}. Opening stock is 0.`);
      setNewProductForm(createDefaultNewProductForm());
      await refreshDashboard();
    } catch (createError) {
      setError(createError.message);
    } finally {
      setCrudBusy(false);
    }
  };

  const handleDraftChange = (productId, field, value) => {
    setAdminDrafts((previous) => ({
      ...previous,
      [productId]: {
        ...(previous[productId] || {}),
        [field]: value
      }
    }));
  };

  const handleUpdateProduct = async (productId) => {
    resetMessages();

    if (!isAdmin) {
      setError("Admin access required.");
      return;
    }

    const draft = adminDrafts[productId];
    if (!draft) {
      setError("Unable to find editable product state.");
      return;
    }

    const quantityValue = Number(draft.quantity);
    if (!Number.isInteger(quantityValue) || quantityValue < 0) {
      setError("Quantity must be a non-negative integer.");
      return;
    }

    setCrudBusy(true);
    try {
      await api.updateProduct(productId, {
        product_name: draft.product_name,
        quantity: quantityValue
      });
      setAdminMessage("Product updated and synced to Excel.");
      await refreshDashboard();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setCrudBusy(false);
    }
  };

  const handleDeleteProduct = async (productId) => {
    resetMessages();

    if (!isAdmin) {
      setError("Admin access required.");
      return;
    }

    setCrudBusy(true);
    try {
      await api.deleteProduct(productId);
      setAdminMessage("Product deleted and Excel file updated.");
      await refreshDashboard();
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setCrudBusy(false);
    }
  };

  const handleRecentLogFilterChange = (event) => {
    const { name, value } = event.target;
    setRecentLogFilters((previous) => ({
      ...previous,
      [name]: value
    }));
  };

  const clearRecentLogFilters = () => {
    setRecentLogFilters({
      category: "all",
      date_from: "",
      date_to: ""
    });
  };

  const summary = dashboard?.summary || {
    products: 0,
    total_quantity: 0,
    zero_stock_products: 0
  };

  const topProducts = dashboard?.top_products || [];
  const dailyNetChanges = dashboard?.daily_net_changes || [];
  const recentLogs = dashboard?.recent_logs || [];
  const excelItems = excelSnapshot?.items || [];
  const excelSummary = excelSnapshot?.summary || {
    product_count: 0,
    total_stock_balance: 0
  };
  const recentLogItems = useMemo(
    () =>
      recentLogs.map((log) => {
        const amount = Number(log.change_amount) || 0;
        const movement = amount > 0 ? "IN" : amount < 0 ? "OUT" : "ADJUST";
        const signedAmount =
          amount > 0 ? `+${Math.abs(amount)}` : amount < 0 ? `-${Math.abs(amount)}` : "0";
        const eventDateValue = log.date || log.created_at;
        const eventDate = eventDateValue ? new Date(eventDateValue) : null;
        const productNameValue = (log.product_name || "").trim();
        const isUniformProduct = Boolean(parseUniformProductName(productNameValue));
        const isWaterBottleProduct = /water\s*bottle/i.test(productNameValue);
        const productCategory = isUniformProduct
          ? "Uniform"
          : isWaterBottleProduct
          ? "Water Bottle"
          : productNameValue || "Unknown";
        const productCategoryKey = isUniformProduct
          ? "uniform"
          : isWaterBottleProduct
          ? "water_bottle"
          : `product:${productCategory.toLowerCase()}`;

        return {
          ...log,
          movement,
          signedAmount,
          productCategory,
          productCategoryKey,
          eventTimestamp: eventDate ? eventDate.getTime() : null,
          eventDateISO: eventDate ? eventDate.toISOString() : "",
          dateLabel: eventDate ? eventDate.toLocaleDateString() : "N/A",
          timeLabel: eventDate
            ? eventDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            : "",
          actorName: log.name || "Unknown",
          actorType: log.class || log.action || "N/A"
        };
      }),
    [recentLogs]
  );
  const recentLogCategoryOptions = useMemo(() => {
    const categoryMap = new Map();
    recentLogItems.forEach((log) => {
      if (!categoryMap.has(log.productCategoryKey)) {
        categoryMap.set(log.productCategoryKey, log.productCategory);
      }
    });

    const pinnedOrder = ["uniform", "water_bottle"];
    const orderedPinned = pinnedOrder
      .filter((key) => categoryMap.has(key))
      .map((key) => ({ key, label: categoryMap.get(key) }));
    const remaining = [...categoryMap.entries()]
      .filter(([key]) => !pinnedOrder.includes(key))
      .map(([key, label]) => ({ key, label }))
      .sort((a, b) => a.label.localeCompare(b.label));

    return [...orderedPinned, ...remaining];
  }, [recentLogItems]);

  useEffect(() => {
    if (
      recentLogFilters.category !== "all" &&
      !recentLogCategoryOptions.some((option) => option.key === recentLogFilters.category)
    ) {
      setRecentLogFilters((previous) => ({
        ...previous,
        category: "all"
      }));
    }
  }, [recentLogCategoryOptions, recentLogFilters.category]);

  const filteredRecentLogItems = useMemo(() => {
    const fromTimestamp = recentLogFilters.date_from
      ? new Date(`${recentLogFilters.date_from}T00:00:00`).getTime()
      : null;
    const toTimestamp = recentLogFilters.date_to
      ? new Date(`${recentLogFilters.date_to}T23:59:59.999`).getTime()
      : null;

    return recentLogItems.filter((log) => {
      if (
        recentLogFilters.category !== "all" &&
        log.productCategoryKey !== recentLogFilters.category
      ) {
        return false;
      }

      if (fromTimestamp !== null && (log.eventTimestamp === null || log.eventTimestamp < fromTimestamp)) {
        return false;
      }

      if (toTimestamp !== null && (log.eventTimestamp === null || log.eventTimestamp > toTimestamp)) {
        return false;
      }

      return true;
    });
  }, [recentLogFilters.category, recentLogFilters.date_from, recentLogFilters.date_to, recentLogItems]);
  const selectedProductBalance = useMemo(() => {
    if (!stockEntryForm.product_name) {
      return null;
    }
    const selected = excelItems.find((item) => item.product_name === stockEntryForm.product_name);
    return selected ? selected.quantity : null;
  }, [excelItems, stockEntryForm.product_name]);
  const stockEntryItemOptions = useMemo(() => getUniformItemOptions("boy"), []);
  const stockEntrySizeOptions = useMemo(() => {
    if (!stockEntryForm.uniform_gender || !stockEntryForm.uniform_item) {
      return [];
    }
    return getUniformSizeOptions(stockEntryForm.uniform_gender, stockEntryForm.uniform_item);
  }, [stockEntryForm.uniform_gender, stockEntryForm.uniform_item]);
  const nonUniformEntryProducts = useMemo(
    () => excelItems.filter((item) => !parseUniformProductName(item.product_name)),
    [excelItems]
  );
  const isUniformStockEntry = stockEntryForm.stock_entry_type !== "other";

  const statCards = useMemo(
    () => [
      { label: "Products", value: summary.products },
      { label: "Total Quantity", value: summary.total_quantity },
      { label: "Zero Stock", value: summary.zero_stock_products }
    ],
    [summary.products, summary.total_quantity, summary.zero_stock_products]
  );

  return (
    <div className="page">
      <div className="grain" />
      <main className="shell">
        <header className="hero panel">
          <div>
            <p className="eyebrow">NiT Product Management</p>
            <h1>Inventory Control Dashboard</h1>
            <p className="lead">
              Monochrome operations view for authentication, Excel ingestion, and
              inventory analytics.
            </p>
          </div>
          <div className="hero-actions">
            {isAuthenticated && isAdmin && (
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setActivePage((previous) =>
                    previous === "dashboard" ? "admin" : "dashboard"
                  )
                }
              >
                {activePage === "dashboard" ? "Admin Page" : "Dashboard"}
              </button>
            )}
            <button
              type="button"
              className="secondary"
              onClick={refreshDashboard}
              disabled={dashboardBusy}
            >
              {dashboardBusy ? "Refreshing..." : "Refresh Data"}
            </button>
            {isAuthenticated ? (
              <button type="button" onClick={handleLogout}>
                Logout
              </button>
            ) : (
              <span className="status-dot">Not logged in</span>
            )}
          </div>
        </header>

        {(error || authMessage || uploadMessage || adminMessage) && (
          <section className="panel message">
            {error && <p className="error">{error}</p>}
            {authMessage && <p className="success">{authMessage}</p>}
            {uploadMessage && <p className="success">{uploadMessage}</p>}
            {adminMessage && <p className="success">{adminMessage}</p>}
          </section>
        )}

        {activePage === "dashboard" ? (
          <section className="layout">
            <div className="stack">
              <article className="panel">
                <div className="section-head">
                  <h2>Authentication</h2>
                  {!isAuthenticated && (
                    <div className="tab-group">
                      <button
                        type="button"
                        className={authMode === "login" ? "tab active" : "tab"}
                        onClick={() => switchMode("login")}
                      >
                        Login
                      </button>
                      <button
                        type="button"
                        className={authMode === "register" ? "tab active" : "tab"}
                        onClick={() => switchMode("register")}
                      >
                        Register
                      </button>
                    </div>
                  )}
                </div>

                {isAuthenticated ? (
                  <div className="auth-summary">
                    <p className="meta">Logged in as: {currentUser?.email}</p>
                    <p className="meta">Role: {isAdmin ? "Admin" : "User"}</p>
                  </div>
                ) : (
                  <form className="form" onSubmit={handleAuthSubmit}>
                    {authMode === "register" && (
                      <label>
                        Username
                        <input
                          name="username"
                          value={authForm.username}
                          onChange={handleAuthChange}
                          required
                        />
                      </label>
                    )}
                    <label>
                      Email
                      <input
                        type="email"
                        name="email"
                        value={authForm.email}
                        onChange={handleAuthChange}
                        required
                      />
                    </label>
                    <label>
                      Password
                      <input
                        type="password"
                        name="password"
                        value={authForm.password}
                        onChange={handleAuthChange}
                        required
                      />
                    </label>
                    <button type="submit" disabled={authBusy}>
                      {authBusy ? "Processing..." : authMode === "login" ? "Login" : "Create Account"}
                    </button>
                  </form>
                )}
              </article>

              <article className="panel">
                <div className="section-head">
                  <h2>Excel Ingestion</h2>
                  <span className="meta">
                    {!isAuthenticated
                      ? "Login required"
                      : isAdmin
                      ? `Admin: ${currentUser?.email}`
                      : "Admin only"}
                  </span>
                </div>
                <form className="form" onSubmit={handleUpload}>
                  <label>
                    Upload `.xlsx`
                    <input
                      type="file"
                      accept=".xlsx,.xls"
                      onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                      disabled={!isAuthenticated || !isAdmin}
                    />
                  </label>
                  <button type="submit" disabled={!isAuthenticated || !isAdmin || uploadBusy}>
                    {uploadBusy ? "Uploading..." : "Load Excel Data"}
                  </button>
                </form>
              </article>

              <article className="stats-grid">
                {statCards.map((card) => (
                  <div className="panel stat-card" key={card.label}>
                    <p>{card.label}</p>
                    <strong>{card.value}</strong>
                  </div>
                ))}
              </article>
            </div>

            <div className="stack wide">
              <article className="panel chart-panel">
                <div className="section-head">
                  <h2>Top Inventory</h2>
                </div>
                <div className="chart-wrap">
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={topProducts}>
                      <CartesianGrid strokeDasharray="2 6" stroke="#5e5e5e" opacity={0.35} />
                      <XAxis dataKey="product_name" stroke="#d4d4d4" tick={{ fontSize: 11 }} />
                      <YAxis stroke="#d4d4d4" tick={{ fontSize: 11 }} />
                      <Tooltip
                        cursor={{ fill: "rgba(255,255,255,0.08)" }}
                        contentStyle={{ background: "#171717", border: "1px solid #535353" }}
                      />
                      <Bar dataKey="quantity" fill="#f2f2f2" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </article>

              <article className="panel chart-panel">
                <div className="section-head">
                  <h2>Daily Net Change</h2>
                </div>
                <div className="chart-wrap">
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={dailyNetChanges}>
                      <CartesianGrid strokeDasharray="2 6" stroke="#5e5e5e" opacity={0.35} />
                      <XAxis dataKey="date" stroke="#d4d4d4" tick={{ fontSize: 11 }} />
                      <YAxis stroke="#d4d4d4" tick={{ fontSize: 11 }} />
                      <Tooltip
                        cursor={{ fill: "rgba(255,255,255,0.08)" }}
                        contentStyle={{ background: "#171717", border: "1px solid #535353" }}
                      />
                      <Area
                        type="monotone"
                        dataKey="net_change"
                        stroke="#f8f8f8"
                        fill="rgba(255, 255, 255, 0.22)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </article>

              <article className="panel">
                <div className="section-head">
                  <h2>Inventory Table</h2>
                  <span className="meta">{inventory.length} items</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Quantity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inventory.map((item) => (
                        <tr key={item.product_name}>
                          <td>{item.product_name}</td>
                          <td>{item.quantity}</td>
                        </tr>
                      ))}
                      {inventory.length === 0 && (
                        <tr>
                          <td colSpan={2}>No inventory data yet. Upload an Excel file.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="panel">
                <div className="section-head">
                  <h2>Recent Changes</h2>
                  <span className="meta">{filteredRecentLogItems.length} events</span>
                </div>
                <div className="log-filters">
                  <label>
                    Product Category
                    <select
                      name="category"
                      value={recentLogFilters.category}
                      onChange={handleRecentLogFilterChange}
                    >
                      <option value="all">All</option>
                      {recentLogCategoryOptions.map((option) => (
                        <option key={option.key} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Date From
                    <input
                      type="date"
                      name="date_from"
                      value={recentLogFilters.date_from}
                      onChange={handleRecentLogFilterChange}
                    />
                  </label>
                  <label>
                    Date To
                    <input
                      type="date"
                      name="date_to"
                      value={recentLogFilters.date_to}
                      onChange={handleRecentLogFilterChange}
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary log-clear-btn"
                    onClick={clearRecentLogFilters}
                    disabled={
                      recentLogFilters.category === "all" &&
                      !recentLogFilters.date_from &&
                      !recentLogFilters.date_to
                    }
                  >
                    Clear
                  </button>
                </div>
                <ul className="log-list">
                  {filteredRecentLogItems.map((log, index) => (
                    <li key={`${log.product_name}-${log.created_at}-${index}`}>
                      <div className="log-main">
                        <div className="log-topline">
                          <span className="log-product">{log.product_name}</span>
                          <span className="log-pill">{log.productCategory}</span>
                        </div>
                        <p className="log-meta">
                          {`${log.movement} | ${Math.abs(Number(log.change_amount) || 0)} | ${log.actorName} (${log.actorType})`}
                        </p>
                        {(log.given_to || log.department) && (
                          <p className="log-meta">
                            {`Given To: ${log.given_to || "N/A"} | Dept: ${log.department || "N/A"}`}
                          </p>
                        )}
                      </div>
                      <strong>{log.signedAmount}</strong>
                      <div className="log-date-block">
                        <time dateTime={log.eventDateISO || undefined}>{log.dateLabel}</time>
                        {log.timeLabel && <span>{log.timeLabel}</span>}
                      </div>
                    </li>
                  ))}
                  {recentLogItems.length === 0 && <li>No change logs yet.</li>}
                  {recentLogItems.length > 0 && filteredRecentLogItems.length === 0 && (
                    <li>No change logs match the selected filters.</li>
                  )}
                </ul>
              </article>
            </div>
          </section>
        ) : (
          <section className="admin-page">
            <article className="panel">
              <div className="section-head">
                <h2>Admin Control Panel</h2>
                <span className="meta">{excelSnapshot.file_path || "app/Services/data.xlsx"}</span>
              </div>

              {!isAuthenticated && (
                <p className="meta">Sign in to access admin stock entry features.</p>
              )}

              {isAuthenticated && !isAdmin && (
                <p className="meta">
                  Your account is authenticated but not listed in `admin_emails`.
                </p>
              )}

              {isAuthenticated && isAdmin && (
                <>
                  <div className="admin-summary-grid">
                    <div className="stat-box">
                      <p>Total Stock Balance</p>
                      <strong>{excelSummary.total_stock_balance}</strong>
                    </div>
                    <div className="stat-box">
                      <p>Products In Excel</p>
                      <strong>{excelSummary.product_count}</strong>
                    </div>
                    <div className="stat-box">
                      <p>Selected Product Balance</p>
                      <strong>{selectedProductBalance ?? "-"}</strong>
                    </div>
                  </div>

                  <form className="form admin-create" onSubmit={handleCreateProduct}>
                    <label>
                      New Product Name
                      <input
                        type="text"
                        name="product_name"
                        value={newProductForm.product_name}
                        onChange={handleNewProductChange}
                        required
                        disabled={crudBusy}
                        placeholder="Enter product name"
                      />
                    </label>
                    <button type="submit" disabled={crudBusy}>
                      {crudBusy ? "Creating..." : "Add Product"}
                    </button>
                  </form>

                  <form className="form admin-entry-form" onSubmit={handleStockEntrySubmit}>
                    <label>
                      Entry Product Type
                      <select
                        name="stock_entry_type"
                        value={stockEntryForm.stock_entry_type}
                        onChange={handleStockEntryChange}
                        disabled={stockEntryBusy}
                      >
                        <option value="uniform">Uniform</option>
                        <option value="other">Other Product</option>
                      </select>
                    </label>
                    {isUniformStockEntry ? (
                      <>
                        <label>
                          Student Type
                          <select
                            name="uniform_gender"
                            value={stockEntryForm.uniform_gender}
                            onChange={handleStockEntryChange}
                            disabled={stockEntryBusy}
                          >
                            <option value="">Select student type</option>
                            <option value="boy">Boy</option>
                            <option value="girl">Girl</option>
                          </select>
                        </label>
                        <label>
                          Uniform Item
                          <select
                            name="uniform_item"
                            value={stockEntryForm.uniform_item}
                            onChange={handleStockEntryChange}
                            required
                            disabled={stockEntryBusy}
                          >
                            <option value="">Select uniform item</option>
                            {stockEntryItemOptions.map((itemOption) => (
                              <option key={itemOption} value={itemOption}>
                                {itemOption === "shirt" ? "Shirt" : "Pant"}
                              </option>
                            ))}
                          </select>
                        </label>
                        {stockEntryForm.uniform_item === "shirt" && (
                          <label>
                            Shirt Type
                            <select
                              name="uniform_sleeve"
                              value={stockEntryForm.uniform_sleeve}
                              onChange={handleStockEntryChange}
                              required
                              disabled={stockEntryBusy}
                            >
                              <option value="">Select shirt type</option>
                              <option value="short">Short</option>
                              <option value="long">Long</option>
                            </select>
                          </label>
                        )}
                        <label>
                          Size
                          <select
                            name="uniform_size"
                            value={stockEntryForm.uniform_size}
                            onChange={handleStockEntryChange}
                            required
                            disabled={
                              stockEntryBusy ||
                              !stockEntryForm.uniform_gender ||
                              !stockEntryForm.uniform_item
                            }
                          >
                            <option value="">Select size</option>
                            {stockEntrySizeOptions.map((sizeOption) => (
                              <option key={sizeOption} value={sizeOption}>
                                {sizeOption}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Uniform Selection
                          <input
                            type="text"
                            value={stockEntryForm.product_name || "No matching product in Excel"}
                            readOnly
                            disabled
                          />
                        </label>
                      </>
                    ) : (
                      <label>
                        Product (from Excel)
                        <select
                          name="other_product_name"
                          value={stockEntryForm.other_product_name}
                          onChange={handleStockEntryChange}
                          required
                          disabled={stockEntryBusy}
                        >
                          <option value="">Select product</option>
                          {nonUniformEntryProducts.map((item) => (
                            <option key={item.product_name} value={item.product_name}>
                              {item.product_name}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    <label>
                      Date
                      <input
                        type="datetime-local"
                        name="entry_date"
                        value={stockEntryForm.entry_date}
                        onChange={handleStockEntryChange}
                        required
                        disabled={stockEntryBusy}
                      />
                    </label>
                    <label>
                      In / Out
                      <select
                        name="movement"
                        value={stockEntryForm.movement}
                        onChange={handleStockEntryChange}
                        disabled={stockEntryBusy}
                      >
                        <option value="in">In</option>
                        <option value="out">Out</option>
                      </select>
                    </label>
                    <label>
                      Quantity
                      <input
                        type="number"
                        min="1"
                        name="quantity"
                        value={stockEntryForm.quantity}
                        onChange={handleStockEntryChange}
                        required
                        disabled={stockEntryBusy}
                      />
                    </label>
                    <label>
                      Given To
                      <input
                        type="text"
                        name="given_to"
                        value={stockEntryForm.given_to}
                        onChange={handleStockEntryChange}
                        required={stockEntryForm.movement === "out"}
                        disabled={stockEntryBusy}
                        placeholder="Receiver name"
                      />
                    </label>
                    <label>
                      Department
                      <input
                        type="text"
                        name="department"
                        value={stockEntryForm.department}
                        onChange={handleStockEntryChange}
                        required={stockEntryForm.movement === "out"}
                        disabled={stockEntryBusy}
                        placeholder="e.g. Sales, IT"
                      />
                    </label>
                    <button type="submit" disabled={stockEntryBusy || excelItems.length === 0}>
                      {stockEntryBusy ? "Saving..." : "Save Stock Entry"}
                    </button>
                  </form>
                </>
              )}
            </article>

            {isAuthenticated && isAdmin && (
              <article className="panel">
                <div className="section-head">
                  <h2>Excel Stock Balance</h2>
                  <span className="meta">{excelItems.length} items</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Stock Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {excelItems.map((item) => (
                        <tr key={item.product_name}>
                          <td>{item.product_name}</td>
                          <td>{item.quantity}</td>
                        </tr>
                      ))}
                      {excelItems.length === 0 && (
                        <tr>
                          <td colSpan={2}>No product data found in `app/Services/data.xlsx`.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </article>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
