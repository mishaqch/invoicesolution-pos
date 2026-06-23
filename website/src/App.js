import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { lazy, Suspense, useEffect } from "react";
import { Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import Home from "@/routes/Home";
// Home loads eagerly (it's the landing page); the rest split into their own
// chunks so first paint only downloads what the visitor actually needs.
const Products = lazy(() => import("@/routes/Products"));
const Features = lazy(() => import("@/routes/Features"));
const Pricing = lazy(() => import("@/routes/Pricing"));
const Industries = lazy(() => import("@/routes/Industries"));
const Support = lazy(() => import("@/routes/Support"));
const Contact = lazy(() => import("@/routes/Contact"));
const About = lazy(() => import("@/routes/About"));
const Privacy = lazy(() => import("@/routes/Privacy"));
const Terms = lazy(() => import("@/routes/Terms"));
const NotFound = lazy(() => import("@/routes/NotFound"));
/** Scroll to top on route change, or to the hash target if one is present. */
function ScrollManager() {
    const { pathname, hash } = useLocation();
    useEffect(() => {
        if (hash) {
            const el = document.getElementById(hash.slice(1));
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            }
        }
        window.scrollTo({ top: 0, behavior: "instant" });
    }, [pathname, hash]);
    return null;
}
/** Lightweight fallback while a lazily-loaded route chunk arrives. */
function RouteFallback() {
    return (_jsx("div", { className: "flex min-h-[60vh] items-center justify-center", children: _jsx("div", { className: "h-9 w-9 animate-spin rounded-full border-[3px] border-brand-100 border-t-brand-600" }) }));
}
function Layout() {
    return (_jsxs("div", { className: "flex min-h-screen flex-col", children: [_jsx(Header, {}), _jsx("main", { className: "flex-1", children: _jsx(Suspense, { fallback: _jsx(RouteFallback, {}), children: _jsx(Outlet, {}) }) }), _jsx(Footer, {})] }));
}
export default function App() {
    return (_jsxs(_Fragment, { children: [_jsx(ScrollManager, {}), _jsx(Routes, { children: _jsxs(Route, { element: _jsx(Layout, {}), children: [_jsx(Route, { path: "/", element: _jsx(Home, {}) }), _jsx(Route, { path: "/products", element: _jsx(Products, {}) }), _jsx(Route, { path: "/features", element: _jsx(Features, {}) }), _jsx(Route, { path: "/pricing", element: _jsx(Pricing, {}) }), _jsx(Route, { path: "/industries", element: _jsx(Industries, {}) }), _jsx(Route, { path: "/support", element: _jsx(Support, {}) }), _jsx(Route, { path: "/contact", element: _jsx(Contact, {}) }), _jsx(Route, { path: "/about", element: _jsx(About, {}) }), _jsx(Route, { path: "/privacy", element: _jsx(Privacy, {}) }), _jsx(Route, { path: "/terms", element: _jsx(Terms, {}) }), _jsx(Route, { path: "*", element: _jsx(NotFound, {}) })] }) })] }));
}
