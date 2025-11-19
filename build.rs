fn main() {
    // Detect if we're being built by maturin
    // Maturin sets PYO3_ENVIRONMENT_SIGNATURE when building
    if std::env::var("PYO3_ENVIRONMENT_SIGNATURE").is_err() {
        eprintln!("\n❌ ERROR: This is a Python extension module!");
        eprintln!("   Don't use 'cargo build' directly.\n");
        eprintln!("   Instead, use:");
        eprintln!("     maturin dev        (for development)");
        eprintln!("     maturin build      (for release builds)\n");
        std::process::exit(1);
    }
}

