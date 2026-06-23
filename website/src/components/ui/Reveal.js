import { jsx as _jsx } from "react/jsx-runtime";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";
/**
 * Scroll-reveal wrapper: children fade + rise into view once, when scrolled
 * near. Respects prefers-reduced-motion (renders instantly, no transform).
 * `delay` staggers siblings; `as` lets it wrap any element.
 */
export function Reveal({ children, className, delay = 0, y = 24, }) {
    const reduce = useReducedMotion();
    if (reduce)
        return _jsx("div", { className: className, children: children });
    return (_jsx(motion.div, { className: cn(className), initial: { opacity: 0, y }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-60px" }, transition: { duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }, children: children }));
}
