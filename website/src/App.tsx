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
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname, hash]);
  return null;
}

/** Lightweight fallback while a lazily-loaded route chunk arrives. */
function RouteFallback() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="h-9 w-9 animate-spin rounded-full border-[3px] border-brand-100 border-t-brand-600" />
    </div>
  );
}

function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}

export default function App() {
  return (
    <>
      <ScrollManager />
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/products" element={<Products />} />
          <Route path="/features" element={<Features />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/industries" element={<Industries />} />
          <Route path="/support" element={<Support />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/about" element={<About />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </>
  );
}
