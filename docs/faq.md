# Frequently Asked Questions

## 1. Can I Use `conda` Instead Of `mamba`?

Yes. In the setup instructions, you can replace `mamba` with `conda` in the
environment commands.

For example:

```bash
conda env create -f env.yml
conda activate gf5
conda env update -f env.yml --prune
```

`mamba` is a drop-in replacement for `conda` with faster environment
resolution. The resulting `gf5` environment should be the same.

## 2. Can I Keep My Custom Code In My Own Git Repository?

Yes. You can set up two Git remotes for your local repository:

- one remote for pulling updates from the teaching repository
- one remote for pushing your own custom code to your personal repository

For example:

```bash
git remote rename origin teaching
git remote add myrepo git@github.com:YOUR_USERNAME/YOUR_REPO.git
```

Then pull course updates from the teaching repository:

```bash
git pull teaching main
```

and push your own work to your repository:

```bash
git push myrepo main
```

Use your actual repository URL in place of
`git@github.com:YOUR_USERNAME/YOUR_REPO.git`.

## 3. Which SMPL Model Should I Download?

See [Part 2: SMPL Model Setup](part2.md#smpl-model-setup) for the detailed
download instructions. The short version is: use the standard SMPL body model
download, unzip it, and place the extracted `smpl/` folder inside `assets/` so
the model files appear under:

```text
assets/smpl/models/
```

## 4. Why Does SMPL Not Load On Windows?

If the blocky/proxy assets load but the real SMPL asset does not, and the
`Use LBS` checkbox stays unavailable, check your PyTorch and NumPy versions.
This Windows failure is tracked in
[GitHub issue #1](https://github.com/CambridgeCVCourses/IIA-Project-GF5/issues/1).

The reported broken environment mixed `torch 2.10.0+cpu` with `numpy 2.4.4`.
That can produce PyTorch DLL loading errors and SMPLX-to-NumPy conversion
errors. One confirmed fix is:

```bash
conda activate gf5
python -m pip uninstall -y torch torchvision torchaudio
python -m pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install numpy==1.26.4 --force-reinstall
```

Then test:

```bash
python -c "import torch; print(torch.__version__)"
python -c "import numpy; print(numpy.__version__)"
python -c "import smplx; print('smplx ok')"
```

Expected versions for this workaround are `torch 2.3.1+cpu` and
`numpy 1.26.4`.

If Windows also reports an OpenMP duplicate-runtime warning, run:

```bat
set KMP_DUPLICATE_LIB_OK=TRUE
python viewer\asset_viewer.py --smpl-model assets\smpl\models\SMPL_MALE.pkl
```

## 5. Why Does The Character Reconstruction Link Fail On Some WiFi Networks?

If the character reconstruction link from the internal Part 3 page works on one
network but fails on another with an error such as
`DNS_PROBE_FINISHED_NXDOMAIN`, the most likely cause is DNS caching or filtering
on that network. This can happen when a subdomain was created recently: one DNS
resolver may know about it, while another may temporarily remember an older
"does not exist" response.

This is not usually a problem with the GF5 code or the reconstruction server.

Temporary fixes:

- try a different network, such as a mobile hotspot
- in Chrome, enable Secure DNS with Cloudflare or Google:
  `Settings -> Privacy and security -> Security -> Use secure DNS`
- wait and try again later, since DNS caches usually expire automatically

If you can reach the page on mobile data but not on WiFi, report the WiFi
network name and the exact browser error message.

## 6. What If The HY-Motion Demo Says I Have Hit A Hugging Face Limit?

The public HY-Motion demo runs on Hugging Face, so anonymous usage can sometimes
hit a rate or quota limit. If this happens, sign up for a free Hugging Face
account and log in before trying the demo again. Free accounts usually receive a
higher quota than anonymous users.
