import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";
import createIntlMiddleware from "next-intl/middleware";
import { locales, defaultLocale } from "./i18n";

// Create i18n middleware
const intlMiddleware = createIntlMiddleware({
  locales,
  defaultLocale,
  localePrefix: "as-needed",
});

// Routes that require authentication
const protectedRoutes = ["/app"];

// Routes that should redirect to /app if already authenticated
const authRoutes = ["/auth/login", "/auth/signup"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip middleware for API routes, static files, etc.
  if (
    pathname.startsWith("/api") ||
    pathname.startsWith("/_next") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // Create a response that we'll modify
  let response = NextResponse.next({
    request: {
      headers: request.headers,
    },
  });

  // Check if Supabase env vars are configured
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  let user = null;

  // Only create Supabase client if env vars are set
  if (supabaseUrl && supabaseKey) {
    const supabase = createServerClient(
      supabaseUrl,
      supabaseKey,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value }) =>
              request.cookies.set(name, value)
            );
            response = NextResponse.next({
              request,
            });
            cookiesToSet.forEach(({ name, value, options }) =>
              response.cookies.set(name, value, options)
            );
          },
        },
      }
    );

    // Refresh session if expired - important for Server Components
    const { data } = await supabase.auth.getUser();
    user = data?.user;
  }

  // Check if accessing protected routes without auth
  const isProtectedRoute = protectedRoutes.some((route) =>
    pathname.startsWith(route)
  );
  const isAuthRoute = authRoutes.some((route) => pathname.includes(route));

  if (isProtectedRoute && !user) {
    // Redirect to login
    const url = request.nextUrl.clone();
    url.pathname = "/auth/login";
    url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(url);
  }

  if (isAuthRoute && user) {
    // Already logged in, redirect to app
    const url = request.nextUrl.clone();
    const redirect = url.searchParams.get("redirect") || "/app";
    url.pathname = redirect;
    url.searchParams.delete("redirect");
    return NextResponse.redirect(url);
  }

  // Apply i18n middleware for locale routing
  // Skip i18n for /app routes (they don't use locale prefix)
  if (!pathname.startsWith("/app") && !pathname.startsWith("/auth")) {
    return intlMiddleware(request);
  }

  return response;
}

export const config = {
  // Match all pathnames except API and static files
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
