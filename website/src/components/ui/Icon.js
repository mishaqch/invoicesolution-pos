import { jsx as _jsx } from "react/jsx-runtime";
/**
 * Explicit icon registry for data-driven icons (feature/industry cards).
 *
 * We deliberately do NOT `import * as Lucide` — that pulls the entire
 * ~1,500-icon library into the main bundle (+400kB). Named imports let the
 * bundler tree-shake to only the icons actually referenced in our data files.
 * When you add a new `icon: "Foo"` to a data file, add `Foo` here too.
 */
import { BadgeCheck, BadgeDollarSign, Banknote, Boxes, Briefcase, CalendarClock, Circle, ClipboardList, Clock, CreditCard, Download, FileCheck2, FileClock, FileSpreadsheet, History, Inbox, KeyRound, LineChart, Monitor, MonitorSmartphone, PauseCircle, Percent, PieChart, Pill, Printer, QrCode, ReceiptText, RefreshCw, ScanLine, ScrollText, Ship, ShieldCheck, ShoppingCart, Smartphone, Split, TriangleAlert, Undo2, UserCog, Users, UtensilsCrossed, Wallet, Warehouse, WifiOff, } from "lucide-react";
const REGISTRY = {
    BadgeCheck,
    BadgeDollarSign,
    Banknote,
    Boxes,
    Briefcase,
    CalendarClock,
    ClipboardList,
    Clock,
    CreditCard,
    Download,
    FileCheck2,
    FileClock,
    FileSpreadsheet,
    History,
    Inbox,
    KeyRound,
    LineChart,
    Monitor,
    MonitorSmartphone,
    PauseCircle,
    Percent,
    PieChart,
    Pill,
    Printer,
    QrCode,
    ReceiptText,
    RefreshCw,
    ScanLine,
    ScrollText,
    Ship,
    ShieldCheck,
    ShoppingCart,
    Smartphone,
    Split,
    TriangleAlert,
    Undo2,
    UserCog,
    Users,
    UtensilsCrossed,
    Wallet,
    Warehouse,
    WifiOff,
};
/** Resolve a registered icon by name; falls back to a neutral dot. */
export function Icon({ name, ...props }) {
    const Cmp = REGISTRY[name] ?? Circle;
    return _jsx(Cmp, { ...props });
}
