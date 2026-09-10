# Publishing the repository

Target repository:

`SepuLeVrai/ha-m2a-water`

## 1. Create the GitHub repository

Create a **public** GitHub repository named:

`ha-m2a-water`

Do not initialize it with another README or license if you are uploading this
package as the initial content.

Recommended description:

`Unofficial Home Assistant integration for m2A / Eaupla! water consumption`

Enable **Issues**.

Recommended topics:

- `home-assistant`
- `hacs`
- `custom-component`
- `water`
- `water-meter`
- `m2a`
- `eaupla`
- `mulhouse`
- `france`

## 2. Upload this repository content

The repository root on GitHub must directly contain:

- `.github/`
- `custom_components/`
- `hacs.json`
- `README.md`
- `CHANGELOG.md`
- `LICENSE`

Do not upload the outer `ha-m2a-water/` directory as a nested directory.

## 3. Check GitHub Actions

Open the **Actions** tab.

Both checks should pass:

- HACS
- Hassfest

## 4. Create the first release

Create a GitHub release with tag:

`v0.1.5`

Suggested release title:

`m2A Eau v0.1.5`

Use the 0.1.5 section from `CHANGELOG.md` as release notes.

## 5. Add it to your own HACS

In HACS, open **Custom repositories** and add:

`https://github.com/SepuLeVrai/ha-m2a-water`

Category:

`Integration`

Then install **m2A Eau** and restart Home Assistant.

## 6. Future versions

For every stable version:

1. update `manifest.json` version;
2. update `CHANGELOG.md`;
3. push/merge to the default branch;
4. wait for HACS + Hassfest to pass;
5. create a GitHub **Release** using the same version as the manifest
   (`v0.x.y` is fine as a release tag).

HACS will then expose the new release as an update.
