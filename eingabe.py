# Inputs section of the app

import streamlit as st

# Title which appear on Streamlit App
st.title("🏠 HypoKompass CH")
st.write("Can I afford this property?")

# Relevant Inputs for the calculation part
purchase_price = st.number_input("Purchase price (CHF)", min_value=100_000, value=1_000_000, step=10_000)
equity = st.number_input("Equity (CHF)", min_value=0, value=250_000, step=10_000)
income = st.number_input("Gross annual income (CHF)", min_value=10_000, value=180_000, step=5_000)
age = st.number_input("Age", min_value=18, max_value=80, value=35, step=1)

# Store inputs for other pages (agreed team interface)
st.session_state["inputs"] = {
    "purchase_price": purchase_price,
    "equity": equity,
    "income": income,
    "age": age,
}

# Plausibility check
if equity >= purchase_price:
    st.info("With this much equity, you don't need a mortgage.")
    st.stop()  # don't run the rest of the page
    
