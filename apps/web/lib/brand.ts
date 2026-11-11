import "server-only";

import { call } from "./api";

export interface Brand {
  product_name: string;
  support_email: string;
  terms_url: string;
  privacy_url: string;
}

export interface SignupCountry {
  code: string;
  name: string;
  region: string;
}

export const FALLBACK_BRAND: Brand = { product_name: "DCS-PIS", support_email: "", terms_url: "", privacy_url: "" };

/** Brand values set in the admin control panel (Body). Falls back to the default name if the API is down. */
export async function getBrand(): Promise<Brand> {
  const r = await call<Brand>("/v1/public/brand", { auth: false, org: false });
  return r.ok ? r.data : FALLBACK_BRAND;
}

/** Countries open for sign-up (Chassis). Empty when the API is unavailable: the form then says so. */
export async function getSignupCountries(): Promise<SignupCountry[]> {
  const r = await call<SignupCountry[]>("/v1/public/countries", { auth: false, org: false });
  return r.ok ? r.data : [];
}
