import type { Finding } from '../types';

/** Extract package metadata from a finding's raw_data (field names vary by tool). */
export function pkgMeta(f: Finding) {
  const d = f.raw_data ?? {};
  const name = (d.PkgName ??
    d.pkg_name ??
    d.package_name ??
    d.packageName ??
    d.component ??
    '') as string;
  const current = (d.InstalledVersion ??
    d.installed_version ??
    d.current_version ??
    d.version ??
    '') as string;
  const fixed = (d.FixedVersion ??
    d.fixed_version ??
    d.fix_version ??
    d.patchedVersions ??
    '') as string;
  const cveId =
    ((d.VulnerabilityID ?? d.vulnerability_id ?? '') as string) ||
    (f.rule_id.match(/^(CVE|GHSA|PRISMA|SNYK)-/i) ? f.rule_id : '');
  return { name, current, fixed, cveId };
}

// Pick the highest semantic-version-ish string from a list of fix candidates.
// Falls back to lexicographic compare for non-semver strings.
export function pickRecommendedVersion(versions: string[]): string {
  const cleaned = versions.map((v) => v.split(',')[0].trim()).filter(Boolean);
  if (cleaned.length === 0) return '';
  return cleaned.sort((a, b) => {
    const pa = a.split('.').map((n) => parseInt(n, 10));
    const pb = b.split('.').map((n) => parseInt(n, 10));
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      const x = pa[i] || 0,
        y = pb[i] || 0;
      if (Number.isFinite(x) && Number.isFinite(y) && x !== y) return y - x;
    }
    return b.localeCompare(a);
  })[0];
}

// Build the package-manager upgrade command for a fixed version, keyed by manifest type.
export function upgradeCmd(name: string, fixed: string, manifestPath: string): string | null {
  if (!name || !fixed) return null;
  const manifest = manifestPath.split('/').pop() ?? '';
  if (manifest.includes('package.json') || manifest.includes('package-lock')) {
    return `npm install ${name}@${fixed}`;
  }
  if (
    manifest.includes('requirements') ||
    manifest.includes('Pipfile') ||
    manifest.endsWith('.txt')
  ) {
    return `pip install ${name}==${fixed}`;
  }
  if (manifest.endsWith('.gradle') || manifest.endsWith('pom.xml') || manifest.endsWith('.jar')) {
    return `# Update ${name} to ${fixed} in your build file`;
  }
  return `# Upgrade ${name} to ${fixed}`;
}
