import { useState, useEffect, useCallback, useRef } from "react"

const API_BASE = window.location.hostname === "localhost" 
  ? "http://localhost:8002" 
  : `http://${window.location.hostname}:8002`

// Types
interface ServiceType {
  id: number
  name: string
  category: string
  base_price: number
  duration_minutes: number
  description?: string
}

interface Barber {
  id: number
  name: string
  commission_rate: number
  specialties?: string
  is_active: boolean
  is_available: boolean
  is_clocked_in?: boolean
  active_orders?: number
}

interface Customer {
  id: number
  name: string
  phone: string
  email?: string
  preferred_barber_id?: number
  preferred_cut?: string
  notes?: string
}

interface QueueEntry {
  id: number
  customer_name: string
  customer_phone?: string
  requested_barber_id?: number
  requested_barber_name?: string
  service_notes?: string
  position: number
  status: string
  estimated_wait?: number
  check_in_time: string
  wait_time_minutes: number
}

interface Order {
  id: number
  customer_id?: number
  customer_name?: string
  barber_id?: number
  barber_name?: string
  status: string
  subtotal: number
  tax: number
  tip: number
  total: number
  services: OrderServiceItem[]
  created_at: string
}

interface OrderServiceItem {
  service_type_id: number
  service_name: string
  quantity: number
  unit_price: number
}

interface OrderService {
  service: ServiceType
  quantity: number
  notes?: string
}

interface Appointment {
  id: number
  customer_name: string
  customer_phone: string
  barber_id?: number
  barber_name?: string
  service_type_id: number
  service_name?: string
  scheduled_time: string
  duration_minutes: number
  status: string
  notes?: string
}

interface TimeSlot {
  time: string
  datetime: string
  available: boolean
}

interface Product {
  id: number
  name: string
  category: string
  price: number
  stock: number
  sku?: string
}

interface CartProduct {
  product: Product
  quantity: number
}

type ViewMode = "pos" | "queue" | "appointments" | "orders" | "shop" | "reports"

const CATEGORIES = [
  { id: "haircut", label: "✂️ Haircuts", color: "blue" },
  { id: "beard", label: "🧔 Beard", color: "amber" },
  { id: "combo", label: "💈 Combos", color: "green" },
  { id: "addon", label: "✨ Add-ons", color: "purple" },
]

function App() {
  // Core state
  const [viewMode, setViewMode] = useState<ViewMode>("pos")
  const [services, setServices] = useState<ServiceType[]>([])
  const [barbers, setBarbers] = useState<Barber[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("haircut")

  // POS state
  const [orderServices, setOrderServices] = useState<OrderService[]>([])
  const [selectedBarber, setSelectedBarber] = useState<Barber | null>(null)
  const [customerPhone, setCustomerPhone] = useState("")
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [customers, setCustomers] = useState<Customer[]>([])
  const searchTimeoutRef = useRef<number | null>(null)

  // Queue state
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [queueStats, setQueueStats] = useState<any>(null)

  // Payment modal
  const [showPaymentModal, setShowPaymentModal] = useState(false)
  const [paymentMethod, setPaymentMethod] = useState("card")
  const [tipAmount, setTipAmount] = useState("")
  const [tipPercentage, setTipPercentage] = useState<number | null>(null)
  const [processingPayment, setProcessingPayment] = useState(false)
  const [completedOrder, setCompletedOrder] = useState<Order | null>(null)

  // New customer modal
  const [showNewCustomerModal, setShowNewCustomerModal] = useState(false)
  const [newCustomerName, setNewCustomerName] = useState("")
  const [newCustomerPhone, setNewCustomerPhone] = useState("")

  // Walk-in modal
  const [showWalkInModal, setShowWalkInModal] = useState(false)
  const [walkInName, setWalkInName] = useState("")
  const [walkInPhone, setWalkInPhone] = useState("")
  const [walkInBarber, setWalkInBarber] = useState<number | null>(null)
  const [walkInNotes, setWalkInNotes] = useState("")

  // Orders
  const [orders, setOrders] = useState<Order[]>([])
  const [orderStatusFilter, setOrderStatusFilter] = useState("all")

  // Reports
  const [dailyReport, setDailyReport] = useState<any>(null)
  const [earningsReport, setEarningsReport] = useState<any>(null)

  // Barber management
  const [showBarberPanel, setShowBarberPanel] = useState(false)

  // Customer profile
  const [showCustomerProfile, setShowCustomerProfile] = useState(false)
  const [customerProfile, setCustomerProfile] = useState<any>(null)
  const [loadingProfile, setLoadingProfile] = useState(false)

  // Cash drawer
  const [showCashDrawer, setShowCashDrawer] = useState(false)
  const [drawerStatus, setDrawerStatus] = useState<any>(null)
  const [cashAmount, setCashAmount] = useState("")
  const [cashNote, setCashNote] = useState("")

  // Products
  const [products, setProducts] = useState<Product[]>([])
  const [productCart, setProductCart] = useState<CartProduct[]>([])
  const [selectedProductCategory, setSelectedProductCategory] = useState("styling")
  const [showProductCheckout, setShowProductCheckout] = useState(false)

  // Feedback
  const [showFeedbackModal, setShowFeedbackModal] = useState(false)
  const [feedbackType, setFeedbackType] = useState<"bug" | "feature">("bug")
  const [feedbackTitle, setFeedbackTitle] = useState("")
  const [feedbackDescription, setFeedbackDescription] = useState("")
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false)

  // Appointments
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [appointmentDate, setAppointmentDate] = useState(new Date().toISOString().split('T')[0])
  const [showAppointmentModal, setShowAppointmentModal] = useState(false)
  const [timeSlots, setTimeSlots] = useState<TimeSlot[]>([])
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null)
  const [selectedServiceForAppt, setSelectedServiceForAppt] = useState<ServiceType | null>(null)
  const [selectedBarberForAppt, setSelectedBarberForAppt] = useState<Barber | null>(null)
  const [apptCustomerName, setApptCustomerName] = useState("")
  const [apptCustomerPhone, setApptCustomerPhone] = useState("")
  const [bookingStep, setBookingStep] = useState<"service" | "time" | "details">("service")

  // Load initial data
  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/services/`).then(r => r.json()),
      fetch(`${API_BASE}/barbers/available`).then(r => r.json()),
    ])
      .then(([servicesData, barbersData]) => {
        setServices(servicesData)
        setBarbers(barbersData)
        if (barbersData.length > 0) {
          setSelectedBarber(barbersData[0])
        }
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  // Load queue when on queue view
  useEffect(() => {
    if (viewMode === "queue") {
      loadQueue()
      loadReports() // Also load today's stats
      const interval = setInterval(loadQueue, 10000) // Refresh every 10s
      return () => clearInterval(interval)
    }
  }, [viewMode])

  // Load orders when on orders view
  useEffect(() => {
    if (viewMode === "orders") {
      loadOrders()
    }
  }, [viewMode, orderStatusFilter])

  // Load reports
  useEffect(() => {
    if (viewMode === "reports") {
      loadReports()
    }
  }, [viewMode])

  // Load appointments
  useEffect(() => {
    if (viewMode === "appointments") {
      loadAppointments()
    }
  }, [viewMode, appointmentDate])

  // Load products
  useEffect(() => {
    if (viewMode === "shop") {
      loadProducts()
    }
  }, [viewMode])

  const loadQueue = async () => {
    try {
      const [queueData, statsData] = await Promise.all([
        fetch(`${API_BASE}/queue/`).then(r => r.json()),
        fetch(`${API_BASE}/queue/stats`).then(r => r.json())
      ])
      setQueue(queueData)
      setQueueStats(statsData)
    } catch (e) {
      console.error("Failed to load queue:", e)
    }
  }

  const loadOrders = async () => {
    try {
      const url = orderStatusFilter === "all" 
        ? `${API_BASE}/orders/` 
        : `${API_BASE}/orders/?status=${orderStatusFilter}`
      const data = await fetch(url).then(r => r.json())
      setOrders(data)
    } catch (e) {
      console.error("Failed to load orders:", e)
    }
  }

  const loadReports = async () => {
    try {
      const [daily, earnings] = await Promise.all([
        fetch(`${API_BASE}/reports/daily`).then(r => r.json()),
        fetch(`${API_BASE}/reports/earnings`).then(r => r.json())
      ])
      setDailyReport(daily)
      setEarningsReport(earnings)
    } catch (e) {
      console.error("Failed to load reports:", e)
    }
  }

  const loadAppointments = async () => {
    try {
      const data = await fetch(`${API_BASE}/appointments/?date=${appointmentDate}`).then(r => r.json())
      setAppointments(data)
    } catch (e) {
      console.error("Failed to load appointments:", e)
    }
  }

  const loadTimeSlots = async () => {
    if (!selectedServiceForAppt) return
    try {
      let url = `${API_BASE}/appointments/available-slots?date=${appointmentDate}&service_type_id=${selectedServiceForAppt.id}`
      if (selectedBarberForAppt) url += `&barber_id=${selectedBarberForAppt.id}`
      const data = await fetch(url).then(r => r.json())
      setTimeSlots(data)
    } catch (e) {
      console.error("Failed to load time slots:", e)
    }
  }

  const bookAppointment = async () => {
    if (!selectedServiceForAppt || !selectedSlot || !apptCustomerName || !apptCustomerPhone) return
    try {
      const res = await fetch(`${API_BASE}/appointments/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: apptCustomerName,
          customer_phone: apptCustomerPhone,
          service_type_id: selectedServiceForAppt.id,
          barber_id: selectedBarberForAppt?.id || null,
          scheduled_time: selectedSlot.datetime,
          duration_minutes: selectedServiceForAppt.duration_minutes
        })
      })
      if (res.ok) {
        setShowAppointmentModal(false)
        resetBookingForm()
        loadAppointments()
      }
    } catch (e) {
      console.error("Failed to book appointment:", e)
    }
  }

  const cancelAppointment = async (id: number) => {
    await fetch(`${API_BASE}/appointments/${id}`, { method: "DELETE" })
    loadAppointments()
  }

  const resetBookingForm = () => {
    setBookingStep("service")
    setSelectedServiceForAppt(null)
    setSelectedBarberForAppt(null)
    setSelectedSlot(null)
    setApptCustomerName("")
    setApptCustomerPhone("")
    setTimeSlots([])
  }

  const clockIn = async (barberId: number) => {
    try {
      await fetch(`${API_BASE}/barbers/${barberId}/clock-in`, { method: "POST" })
      refreshBarbers()
    } catch (e) {
      console.error("Clock in failed:", e)
    }
  }

  const clockOut = async (barberId: number) => {
    try {
      await fetch(`${API_BASE}/barbers/${barberId}/clock-out`, { method: "POST" })
      refreshBarbers()
    } catch (e) {
      console.error("Clock out failed:", e)
    }
  }

  const refreshBarbers = async () => {
    const data = await fetch(`${API_BASE}/barbers/available`).then(r => r.json())
    setBarbers(data)
  }

  const fetchCustomerProfile = async (customerId: number) => {
    setLoadingProfile(true)
    try {
      const data = await fetch(`${API_BASE}/customers/${customerId}/history`).then(r => r.json())
      setCustomerProfile(data)
      setShowCustomerProfile(true)
    } catch (e) {
      console.error("Failed to load profile:", e)
    }
    setLoadingProfile(false)
  }

  const loadDrawerStatus = async () => {
    const data = await fetch(`${API_BASE}/cash-drawer/status`).then(r => r.json())
    setDrawerStatus(data)
  }

  const openDrawer = async () => {
    const amount = parseFloat(cashAmount) || 200
    await fetch(`${API_BASE}/cash-drawer/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ starting_cash: amount })
    })
    loadDrawerStatus()
    setCashAmount("")
  }

  const closeDrawer = async () => {
    await fetch(`${API_BASE}/cash-drawer/close`, { method: "POST" })
    loadDrawerStatus()
  }

  const addCash = async () => {
    const amount = parseFloat(cashAmount)
    if (!amount) return
    await fetch(`${API_BASE}/cash-drawer/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, note: cashNote || null })
    })
    loadDrawerStatus()
    setCashAmount("")
    setCashNote("")
  }

  const removeCash = async () => {
    const amount = parseFloat(cashAmount)
    if (!amount) return
    await fetch(`${API_BASE}/cash-drawer/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, note: cashNote || null })
    })
    loadDrawerStatus()
    setCashAmount("")
    setCashNote("")
  }

  const loadProducts = async () => {
    const data = await fetch(`${API_BASE}/products/`).then(r => r.json())
    setProducts(data)
  }

  const addToProductCart = (product: Product) => {
    const existing = productCart.find(cp => cp.product.id === product.id)
    if (existing) {
      setProductCart(productCart.map(cp =>
        cp.product.id === product.id ? { ...cp, quantity: cp.quantity + 1 } : cp
      ))
    } else {
      setProductCart([...productCart, { product, quantity: 1 }])
    }
  }

  const removeFromProductCart = (index: number) => {
    setProductCart(productCart.filter((_, i) => i !== index))
  }

  const productSubtotal = productCart.reduce(
    (sum, cp) => sum + cp.product.price * cp.quantity,
    0
  )
  const productTax = productSubtotal * 0.0875
  const productTotal = productSubtotal + productTax

  const processProductSale = async () => {
    await fetch(`${API_BASE}/products/sell`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(productCart.map(cp => ({
        product_id: cp.product.id,
        quantity: cp.quantity
      })))
    })
    setProductCart([])
    setShowProductCheckout(false)
    loadProducts()
  }

  const submitFeedback = async () => {
    if (!feedbackTitle.trim() || !feedbackDescription.trim()) return
    await fetch(`${API_BASE}/feedback/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: feedbackType,
        title: feedbackTitle.trim(),
        description: feedbackDescription.trim(),
        page_url: window.location.href,
        user_agent: navigator.userAgent
      })
    })
    setFeedbackSubmitted(true)
    setTimeout(() => {
      setShowFeedbackModal(false)
      setFeedbackSubmitted(false)
      setFeedbackTitle("")
      setFeedbackDescription("")
    }, 2000)
  }

  const searchCustomers = useCallback(async (phone: string) => {
    if (phone.length < 3) {
      setCustomers([])
      return
    }
    try {
      const res = await fetch(`${API_BASE}/customers/search?q=${encodeURIComponent(phone)}`)
      const data = await res.json()
      setCustomers(data)
    } catch (e) {
      console.error(e)
    }
  }, [])

  const handlePhoneChange = (value: string) => {
    setCustomerPhone(value)
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    searchTimeoutRef.current = window.setTimeout(() => {
      searchCustomers(value)
    }, 300)
  }

  const addService = (service: ServiceType) => {
    const existing = orderServices.find(os => os.service.id === service.id)
    if (existing) {
      setOrderServices(orderServices.map(os =>
        os.service.id === service.id ? { ...os, quantity: os.quantity + 1 } : os
      ))
    } else {
      setOrderServices([...orderServices, { service, quantity: 1 }])
    }
  }

  const removeService = (index: number) => {
    setOrderServices(orderServices.filter((_, i) => i !== index))
  }

  const subtotal = orderServices.reduce(
    (sum, os) => sum + os.service.base_price * os.quantity,
    0
  )
  const tax = subtotal * 0.0875
  const tip = parseFloat(tipAmount) || 0
  const total = subtotal + tax + tip

  const setTipByPercentage = (pct: number) => {
    setTipPercentage(pct)
    setTipAmount((subtotal * pct / 100).toFixed(2))
  }

  const createCustomer = async () => {
    if (!newCustomerName.trim() || !newCustomerPhone.trim()) return
    try {
      const res = await fetch(`${API_BASE}/customers/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newCustomerName.trim(),
          phone: newCustomerPhone.trim()
        })
      })
      if (res.ok) {
        const newCust = await res.json()
        setCustomer(newCust)
        setCustomerPhone(newCust.phone)
        setShowNewCustomerModal(false)
        setNewCustomerName("")
        setNewCustomerPhone("")
      }
    } catch (e) {
      console.error(e)
    }
  }

  const addToQueue = async () => {
    if (!walkInName.trim()) return
    try {
      await fetch(`${API_BASE}/queue/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: walkInName.trim(),
          customer_phone: walkInPhone.trim() || null,
          requested_barber_id: walkInBarber,
          service_notes: walkInNotes.trim() || null
        })
      })
      setShowWalkInModal(false)
      setWalkInName("")
      setWalkInPhone("")
      setWalkInBarber(null)
      setWalkInNotes("")
      loadQueue()
    } catch (e) {
      console.error(e)
    }
  }

  const callCustomer = async (entryId: number) => {
    await fetch(`${API_BASE}/queue/${entryId}/call`, { method: "POST" })
    loadQueue()
  }

  const removeFromQueue = async (entryId: number) => {
    await fetch(`${API_BASE}/queue/${entryId}/remove`, { method: "POST" })
    loadQueue()
  }

  const processPayment = async () => {
    if (orderServices.length === 0) return
    setProcessingPayment(true)

    try {
      // Create order
      const orderRes = await fetch(`${API_BASE}/orders/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customer?.id || null,
          barber_id: selectedBarber?.id || null,
          services: orderServices.map(os => ({
            service_type_id: os.service.id,
            quantity: os.quantity,
            notes: os.notes || null
          }))
        })
      })

      if (!orderRes.ok) throw new Error("Order failed")
      const orderData = await orderRes.json()

      // Process payment
      await fetch(`${API_BASE}/payments/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: orderData.id,
          amount: subtotal + tax,
          tip_amount: tip,
          method: paymentMethod
        })
      })

      // Record cash sale if paid in cash
      if (paymentMethod === "cash") {
        await fetch(`${API_BASE}/cash-drawer/sale`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: subtotal + tax + tip,
            note: `Order #${orderData.id}`
          })
        })
      }

      // Get updated order
      const updated = await fetch(`${API_BASE}/orders/${orderData.id}`).then(r => r.json())
      setCompletedOrder(updated)
      setShowPaymentModal(false)
    } catch (e) {
      console.error("Payment error:", e)
      alert("Payment failed")
    }
    setProcessingPayment(false)
  }

  const newOrder = () => {
    setOrderServices([])
    setCustomer(null)
    setCustomerPhone("")
    setCompletedOrder(null)
    setTipAmount("")
    setTipPercentage(null)
  }

  const filteredServices = services.filter(s => s.category === selectedCategory)

  if (loading) return <div className="p-8 text-center text-xl">Loading...</div>
  if (error) return <div className="p-8 text-center text-red-500">Error: {error}</div>

  // Completed order screen
  if (completedOrder) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-slate-100 p-8 flex items-center justify-center">
        <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full text-center print-receipt">
          {/* Receipt Header */}
          <div className="text-4xl mb-2">💈</div>
          <h2 className="text-xl font-bold">Classic Cuts Barbershop</h2>
          <p className="text-sm text-gray-500">123 Main Street</p>
          <p className="text-sm text-gray-500 mb-4">(555) 123-4567</p>
          
          <div className="border-t border-b py-2 mb-4">
            <p className="text-sm text-gray-500">Order #{completedOrder.id}</p>
            <p className="text-sm text-gray-500">{new Date().toLocaleString()}</p>
            {customer && <p className="font-semibold">{customer.name}</p>}
            {selectedBarber && <p className="text-sm text-blue-600">Barber: {selectedBarber.name}</p>}
          </div>

          <div className="text-left mb-4">
            {completedOrder.services.map((s, i) => (
              <div key={i} className="flex justify-between py-1 text-sm">
                <span>{s.quantity}x {s.service_name}</span>
                <span>${(s.unit_price * s.quantity).toFixed(2)}</span>
              </div>
            ))}
          </div>
          
          <div className="border-t pt-3 space-y-1 text-sm">
            <div className="flex justify-between text-gray-600">
              <span>Subtotal</span>
              <span>${completedOrder.subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>Tax (8.75%)</span>
              <span>${completedOrder.tax.toFixed(2)}</span>
            </div>
            {completedOrder.tip > 0 && (
              <div className="flex justify-between text-green-600">
                <span>Tip (Thank you! 🙏)</span>
                <span>${completedOrder.tip.toFixed(2)}</span>
              </div>
            )}
            <div className="flex justify-between text-xl font-bold pt-2 border-t">
              <span>TOTAL</span>
              <span>${completedOrder.total.toFixed(2)}</span>
            </div>
          </div>
          
          <p className="text-center mt-4 text-sm text-gray-500">Thanks for visiting! See you next time!</p>

          <div className="flex gap-3 mt-6 no-print">
            <button
              onClick={() => window.print()}
              className="flex-1 py-4 bg-gray-200 rounded-xl font-bold text-lg hover:bg-gray-300"
            >
              🖨️ Print
            </button>
            <button
              onClick={newOrder}
              className="flex-1 py-4 bg-blue-600 text-white rounded-xl font-bold text-lg hover:bg-blue-700"
            >
              Next Customer
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Payment Modal
  const PaymentModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-lg w-full mx-4">
        <h2 className="text-2xl font-bold mb-6 text-center">Payment</h2>

        <div className="bg-gray-50 rounded-lg p-4 mb-6">
          <div className="flex justify-between mb-2">
            <span>Subtotal</span>
            <span>${subtotal.toFixed(2)}</span>
          </div>
          <div className="flex justify-between mb-2">
            <span>Tax (8.75%)</span>
            <span>${tax.toFixed(2)}</span>
          </div>

          <div className="border-t pt-3 mt-3">
            <p className="text-sm font-semibold text-gray-700 mb-2">Add Tip</p>
            <div className="grid grid-cols-4 gap-2 mb-2">
              {[15, 18, 20, 25].map(pct => (
                <button
                  key={pct}
                  onClick={() => setTipByPercentage(pct)}
                  className={`py-2 rounded-lg text-sm font-semibold transition ${
                    tipPercentage === pct
                      ? "bg-blue-600 text-white"
                      : "bg-gray-200 hover:bg-gray-300"
                  }`}
                >
                  {pct}%
                </button>
              ))}
            </div>
            <input
              type="number"
              placeholder="Custom tip"
              value={tipAmount}
              onChange={e => { setTipAmount(e.target.value); setTipPercentage(null) }}
              className="w-full p-2 border rounded-lg"
            />
          </div>

          <div className="flex justify-between text-2xl font-bold pt-3 mt-3 border-t">
            <span>Total</span>
            <span className="text-green-600">${total.toFixed(2)}</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { id: "card", label: "💳 Card" },
            { id: "cash", label: "💵 Cash" },
            { id: "apple_pay", label: "🍎 Apple Pay" },
          ].map(method => (
            <button
              key={method.id}
              onClick={() => setPaymentMethod(method.id)}
              className={`p-4 rounded-xl border-2 transition ${
                paymentMethod === method.id
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <div className="text-center font-semibold">{method.label}</div>
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => setShowPaymentModal(false)}
            className="flex-1 py-4 bg-gray-200 rounded-xl font-bold hover:bg-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={processPayment}
            disabled={processingPayment}
            className="flex-1 py-4 bg-green-600 text-white rounded-xl font-bold hover:bg-green-700 disabled:bg-gray-300"
          >
            {processingPayment ? "Processing..." : "Complete"}
          </button>
        </div>
      </div>
    </div>
  )

  // New Customer Modal
  const NewCustomerModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">
        <h2 className="text-2xl font-bold mb-6 text-center">New Customer</h2>
        <div className="space-y-4">
          <input
            type="text"
            placeholder="Name"
            value={newCustomerName}
            onChange={e => setNewCustomerName(e.target.value)}
            className="w-full p-3 border-2 rounded-lg"
          />
          <input
            type="tel"
            placeholder="Phone"
            value={newCustomerPhone}
            onChange={e => setNewCustomerPhone(e.target.value)}
            className="w-full p-3 border-2 rounded-lg"
          />
        </div>
        <div className="flex gap-3 mt-6">
          <button
            onClick={() => setShowNewCustomerModal(false)}
            className="flex-1 py-4 bg-gray-200 rounded-xl font-bold hover:bg-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={createCustomer}
            disabled={!newCustomerName || !newCustomerPhone}
            className="flex-1 py-4 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 disabled:bg-gray-300"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  )

  // Walk-in Modal
  const WalkInModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">
        <h2 className="text-2xl font-bold mb-6 text-center">Add to Queue</h2>
        <div className="space-y-4">
          <input
            type="text"
            placeholder="Customer Name *"
            value={walkInName}
            onChange={e => setWalkInName(e.target.value)}
            className="w-full p-3 border-2 rounded-lg"
          />
          <input
            type="tel"
            placeholder="Phone (optional)"
            value={walkInPhone}
            onChange={e => setWalkInPhone(e.target.value)}
            className="w-full p-3 border-2 rounded-lg"
          />
          <select
            value={walkInBarber || ""}
            onChange={e => setWalkInBarber(e.target.value ? parseInt(e.target.value) : null)}
            className="w-full p-3 border-2 rounded-lg"
          >
            <option value="">Any available barber</option>
            {barbers.map(b => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Service notes (optional)"
            value={walkInNotes}
            onChange={e => setWalkInNotes(e.target.value)}
            className="w-full p-3 border-2 rounded-lg"
          />
        </div>
        <div className="flex gap-3 mt-6">
          <button
            onClick={() => setShowWalkInModal(false)}
            className="flex-1 py-4 bg-gray-200 rounded-xl font-bold hover:bg-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={addToQueue}
            disabled={!walkInName}
            className="flex-1 py-4 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 disabled:bg-gray-300"
          >
            Add to Queue
          </button>
        </div>
      </div>
    </div>
  )

  // Queue View
  const QueueView = () => (
    <div className="max-w-4xl mx-auto">
      {/* Today's quick stats */}
      {dailyReport && (
        <div className="bg-gradient-to-r from-blue-600 to-slate-700 rounded-xl shadow-lg p-6 mb-6 text-white">
          <h3 className="text-lg font-semibold mb-3 opacity-80">Today's Performance</h3>
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold">${dailyReport.summary.total_revenue.toFixed(0)}</div>
              <div className="text-sm opacity-70">Revenue</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold">{dailyReport.summary.num_customers}</div>
              <div className="text-sm opacity-70">Customers</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold">${dailyReport.summary.total_tips.toFixed(0)}</div>
              <div className="text-sm opacity-70">Tips</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold">${dailyReport.summary.average_ticket.toFixed(0)}</div>
              <div className="text-sm opacity-70">Avg Ticket</div>
            </div>
          </div>
        </div>
      )}
      
      <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
        <div className="flex justify-between items-center">
          <h2 className="text-2xl font-bold">📋 Walk-in Queue</h2>
          <button
            onClick={() => setShowWalkInModal(true)}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-bold hover:bg-blue-700"
          >
            ➕ Add Walk-in
          </button>
        </div>
        {queueStats && (
          <div className="grid grid-cols-4 gap-4 mt-4">
            <div className="bg-yellow-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-yellow-600">{queueStats.waiting}</div>
              <div className="text-sm text-gray-600">Waiting</div>
            </div>
            <div className="bg-blue-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-blue-600">{queueStats.called}</div>
              <div className="text-sm text-gray-600">Called</div>
            </div>
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-green-600">{queueStats.in_service}</div>
              <div className="text-sm text-gray-600">In Service</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-purple-600">{queueStats.estimated_wait_new} min</div>
              <div className="text-sm text-gray-600">Est. Wait</div>
            </div>
          </div>
        )}
      </div>

      {queue.length === 0 ? (
        <div className="bg-white rounded-xl shadow-lg p-12 text-center text-gray-500">
          No customers in queue
        </div>
      ) : (
        <div className="space-y-4">
          {queue.map((entry, index) => (
            <div
              key={entry.id}
              className={`bg-white rounded-xl shadow-lg p-6 border-l-4 ${
                entry.status === "called" ? "border-blue-500 bg-blue-50" : "border-gray-200"
              }`}
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="text-2xl font-bold text-gray-400">#{entry.position}</span>
                    <span className="text-xl font-bold">{entry.customer_name}</span>
                    {entry.status === "called" && (
                      <span className="px-2 py-1 bg-blue-600 text-white rounded text-sm font-bold">
                        CALLED
                      </span>
                    )}
                  </div>
                  {entry.customer_phone && (
                    <p className="text-gray-500">{entry.customer_phone}</p>
                  )}
                  {entry.requested_barber_name && (
                    <p className="text-sm text-blue-600">Requested: {entry.requested_barber_name}</p>
                  )}
                  {entry.service_notes && (
                    <p className="text-sm text-gray-500 italic">{entry.service_notes}</p>
                  )}
                  <p className="text-sm text-gray-400 mt-2">
                    Waiting: {entry.wait_time_minutes} min
                  </p>
                </div>
                <div className="flex gap-2">
                  {entry.status === "waiting" && (
                    <button
                      onClick={() => callCustomer(entry.id)}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700"
                    >
                      📢 Call
                    </button>
                  )}
                  {entry.status === "called" && (
                    <button
                      onClick={() => {
                        // Start service - go to POS
                        setViewMode("pos")
                        // Pre-fill customer name if available
                        if (entry.customer_phone) {
                          setCustomerPhone(entry.customer_phone)
                          searchCustomers(entry.customer_phone)
                        }
                      }}
                      className="px-4 py-2 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700"
                    >
                      ✂️ Start Service
                    </button>
                  )}
                  <button
                    onClick={() => removeFromQueue(entry.id)}
                    className="px-4 py-2 bg-red-100 text-red-600 rounded-lg font-semibold hover:bg-red-200"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  // Orders View
  const OrdersView = () => (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold">📋 Orders</h2>
          <div className="flex gap-2">
            {["all", "waiting", "in_progress", "completed"].map(status => (
              <button
                key={status}
                onClick={() => setOrderStatusFilter(status)}
                className={`px-4 py-2 rounded-lg font-semibold ${
                  orderStatusFilter === status
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 hover:bg-gray-200"
                }`}
              >
                {status === "all" ? "All" : status.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
      </div>

      {orders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-lg p-12 text-center text-gray-500">
          No orders found
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left">Order</th>
                <th className="px-4 py-3 text-left">Customer</th>
                <th className="px-4 py-3 text-left">Barber</th>
                <th className="px-4 py-3 text-left">Services</th>
                <th className="px-4 py-3 text-left">Total</th>
                <th className="px-4 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {orders.map(order => (
                <tr key={order.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-bold">#{order.id}</td>
                  <td className="px-4 py-3">{order.customer_name || "Walk-in"}</td>
                  <td className="px-4 py-3">{order.barber_name || "-"}</td>
                  <td className="px-4 py-3 text-sm">{order.services.map(s => s.service_name).join(", ")}</td>
                  <td className="px-4 py-3 font-semibold">${order.total.toFixed(2)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-sm font-semibold ${
                      order.status === "completed" ? "bg-green-100 text-green-800" :
                      order.status === "in_progress" ? "bg-blue-100 text-blue-800" :
                      "bg-yellow-100 text-yellow-800"
                    }`}>
                      {order.status.replace("_", " ").toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )

  // Feedback Modal
  const FeedbackModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]">
      <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-lg w-full mx-4">
        {feedbackSubmitted ? (
          <div className="text-center py-8">
            <div className="text-5xl mb-4">✅</div>
            <h2 className="text-2xl font-bold text-green-600">Thank you!</h2>
            <p className="text-gray-500 mt-2">Your feedback has been submitted.</p>
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">📝 Send Feedback</h2>
              <button onClick={() => setShowFeedbackModal(false)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setFeedbackType("bug")}
                className={`flex-1 py-3 rounded-lg font-semibold transition ${
                  feedbackType === "bug" ? "bg-red-600 text-white" : "bg-gray-100 hover:bg-gray-200"
                }`}
              >
                🐛 Bug Report
              </button>
              <button
                onClick={() => setFeedbackType("feature")}
                className={`flex-1 py-3 rounded-lg font-semibold transition ${
                  feedbackType === "feature" ? "bg-blue-600 text-white" : "bg-gray-100 hover:bg-gray-200"
                }`}
              >
                💡 Feature Request
              </button>
            </div>
            
            <div className="space-y-4">
              <input
                type="text"
                placeholder={feedbackType === "bug" ? "What went wrong?" : "What would you like?"}
                value={feedbackTitle}
                onChange={e => setFeedbackTitle(e.target.value)}
                className="w-full p-3 border-2 rounded-lg focus:border-blue-500 focus:outline-none"
              />
              <textarea
                placeholder="Describe in detail..."
                value={feedbackDescription}
                onChange={e => setFeedbackDescription(e.target.value)}
                rows={4}
                className="w-full p-3 border-2 rounded-lg focus:border-blue-500 focus:outline-none resize-none"
              />
            </div>
            
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowFeedbackModal(false)}
                className="flex-1 py-3 bg-gray-200 rounded-lg font-semibold hover:bg-gray-300"
              >
                Cancel
              </button>
              <button
                onClick={submitFeedback}
                disabled={!feedbackTitle.trim() || !feedbackDescription.trim()}
                className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-300"
              >
                Submit
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )

  // Cash Drawer Modal
  const CashDrawerModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold">💰 Cash Drawer</h2>
          <button onClick={() => setShowCashDrawer(false)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
        </div>
        
        {drawerStatus && (
          <>
            <div className={`p-4 rounded-lg mb-6 ${drawerStatus.is_open ? "bg-green-50" : "bg-gray-50"}`}>
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-3 h-3 rounded-full ${drawerStatus.is_open ? "bg-green-500" : "bg-gray-400"}`}></span>
                <span className="font-semibold">{drawerStatus.is_open ? "Drawer Open" : "Drawer Closed"}</span>
              </div>
              
              {drawerStatus.is_open && (
                <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
                  <div>
                    <div className="text-gray-500">Starting</div>
                    <div className="font-bold">${drawerStatus.starting_cash.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Cash Sales</div>
                    <div className="font-bold text-green-600">${drawerStatus.cash_sales.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Added</div>
                    <div className="font-bold text-blue-600">+${drawerStatus.cash_added.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Removed</div>
                    <div className="font-bold text-red-600">-${drawerStatus.cash_removed.toFixed(2)}</div>
                  </div>
                </div>
              )}
              
              {drawerStatus.is_open && (
                <div className="mt-4 pt-4 border-t">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold">Current Cash</span>
                    <span className="text-2xl font-bold text-green-600">${drawerStatus.current_cash.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </div>
            
            {!drawerStatus.is_open ? (
              <div>
                <label className="text-sm font-semibold text-gray-600">Starting Cash</label>
                <input
                  type="number"
                  placeholder="200.00"
                  value={cashAmount}
                  onChange={e => setCashAmount(e.target.value)}
                  className="w-full p-3 border rounded-lg mb-4"
                />
                <button
                  onClick={openDrawer}
                  className="w-full py-3 bg-green-600 text-white rounded-lg font-bold hover:bg-green-700"
                >
                  Open Drawer
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder="Amount"
                    value={cashAmount}
                    onChange={e => setCashAmount(e.target.value)}
                    className="flex-1 p-3 border rounded-lg"
                  />
                  <input
                    type="text"
                    placeholder="Note (optional)"
                    value={cashNote}
                    onChange={e => setCashNote(e.target.value)}
                    className="flex-1 p-3 border rounded-lg"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={addCash}
                    disabled={!cashAmount}
                    className="py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-300"
                  >
                    + Add Cash
                  </button>
                  <button
                    onClick={removeCash}
                    disabled={!cashAmount}
                    className="py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 disabled:bg-gray-300"
                  >
                    - Remove Cash
                  </button>
                </div>
                <button
                  onClick={closeDrawer}
                  className="w-full py-3 bg-red-600 text-white rounded-lg font-bold hover:bg-red-700"
                >
                  Close & Reconcile
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )

  // Customer Profile Modal
  const CustomerProfileModal = () => {
    if (!customerProfile) return null
    const { customer: cust, stats, recent_visits } = customerProfile
    
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-slate-700 p-6 rounded-t-2xl text-white">
            <div className="flex justify-between items-start">
              <div>
                <h2 className="text-2xl font-bold">{cust.name}</h2>
                <p className="text-blue-100">{cust.phone}</p>
                {cust.email && <p className="text-blue-100 text-sm">{cust.email}</p>}
              </div>
              <button 
                onClick={() => setShowCustomerProfile(false)}
                className="text-white/80 hover:text-white text-2xl"
              >
                ✕
              </button>
            </div>
            {cust.preferred_cut && (
              <div className="mt-3 bg-white/20 rounded-lg px-3 py-2 text-sm">
                ✂️ Preferred: {cust.preferred_cut}
              </div>
            )}
          </div>
          
          {/* Stats */}
          <div className="grid grid-cols-4 gap-4 p-6 bg-gray-50">
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">{stats.total_visits}</div>
              <div className="text-sm text-gray-500">Total Visits</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">${stats.total_spent.toFixed(0)}</div>
              <div className="text-sm text-gray-500">Total Spent</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">${stats.average_spend.toFixed(0)}</div>
              <div className="text-sm text-gray-500">Avg per Visit</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-amber-600">${stats.average_tip.toFixed(0)}</div>
              <div className="text-sm text-gray-500">Avg Tip</div>
            </div>
          </div>
          
          {/* Favorite Services */}
          {stats.favorite_services.length > 0 && (
            <div className="p-6 border-b">
              <h3 className="font-bold text-gray-700 mb-3">💈 Favorite Services</h3>
              <div className="flex flex-wrap gap-2">
                {stats.favorite_services.map((s: any, i: number) => (
                  <span key={i} className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm">
                    {s.name} ({s.count}x)
                  </span>
                ))}
              </div>
            </div>
          )}
          
          {/* Notes */}
          {cust.notes && (
            <div className="p-6 border-b">
              <h3 className="font-bold text-gray-700 mb-2">📝 Notes</h3>
              <p className="text-gray-600 bg-yellow-50 p-3 rounded-lg">{cust.notes}</p>
            </div>
          )}
          
          {/* Recent Visits */}
          <div className="p-6">
            <h3 className="font-bold text-gray-700 mb-3">🕐 Recent Visits</h3>
            {recent_visits.length === 0 ? (
              <p className="text-gray-400 text-center py-4">No visits yet</p>
            ) : (
              <div className="space-y-3">
                {recent_visits.slice(0, 5).map((visit: any) => (
                  <div key={visit.order_id} className="bg-gray-50 rounded-lg p-3">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-sm text-gray-500">
                        {new Date(visit.date).toLocaleDateString()} · Order #{visit.order_id}
                      </span>
                      <span className="font-bold text-green-600">${visit.total.toFixed(2)}</span>
                    </div>
                    <div className="text-sm">
                      {visit.services.map((s: any, i: number) => (
                        <span key={i} className="mr-2">{s.name}</span>
                      ))}
                    </div>
                    {visit.tip > 0 && (
                      <div className="text-xs text-gray-500 mt-1">Tip: ${visit.tip.toFixed(2)}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
          
          {/* Footer */}
          <div className="p-6 border-t bg-gray-50 rounded-b-2xl">
            <p className="text-center text-sm text-gray-500">
              Member since {new Date(cust.member_since).toLocaleDateString()}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Barber Panel
  const BarberPanel = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold">👔 Barber Management</h2>
          <button onClick={() => setShowBarberPanel(false)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
        </div>
        
        <div className="space-y-4">
          {barbers.map(b => (
            <div key={b.id} className="flex items-center justify-between bg-gray-50 rounded-lg p-4">
              <div>
                <div className="font-semibold text-lg">{b.name}</div>
                <div className="flex items-center gap-2 text-sm">
                  {b.is_clocked_in ? (
                    <span className="text-green-600 flex items-center gap-1">
                      <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                      Clocked In
                    </span>
                  ) : (
                    <span className="text-gray-500">Not clocked in</span>
                  )}
                  {b.active_orders && b.active_orders > 0 && (
                    <span className="text-blue-600">· {b.active_orders} active</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => b.is_clocked_in ? clockOut(b.id) : clockIn(b.id)}
                className={`px-4 py-2 rounded-lg font-semibold ${
                  b.is_clocked_in
                    ? "bg-red-100 text-red-600 hover:bg-red-200"
                    : "bg-green-100 text-green-600 hover:bg-green-200"
                }`}
              >
                {b.is_clocked_in ? "Clock Out" : "Clock In"}
              </button>
            </div>
          ))}
        </div>
        
        <button
          onClick={() => setShowBarberPanel(false)}
          className="w-full mt-6 py-3 bg-gray-200 rounded-lg font-semibold hover:bg-gray-300"
        >
          Close
        </button>
      </div>
    </div>
  )

  // Appointment Booking Modal
  const AppointmentModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold">📅 Book Appointment</h2>
          <button onClick={() => { setShowAppointmentModal(false); resetBookingForm() }} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
        </div>

        {/* Progress Steps */}
        <div className="flex gap-4 mb-6">
          {["service", "time", "details"].map((step, i) => (
            <div key={step} className={`flex-1 h-2 rounded ${
              bookingStep === step ? "bg-blue-600" :
              (step === "service" || (step === "time" && bookingStep === "details")) ? "bg-blue-300" : "bg-gray-200"
            }`} />
          ))}
        </div>

        {/* Step 1: Select Service */}
        {bookingStep === "service" && (
          <div>
            <h3 className="font-semibold mb-4">Select Service</h3>
            <div className="grid grid-cols-2 gap-3 max-h-80 overflow-y-auto">
              {services.map(svc => (
                <button
                  key={svc.id}
                  onClick={() => setSelectedServiceForAppt(svc)}
                  className={`p-4 rounded-lg border-2 text-left transition ${
                    selectedServiceForAppt?.id === svc.id
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 hover:border-blue-300"
                  }`}
                >
                  <div className="font-semibold">{svc.name}</div>
                  <div className="text-sm text-gray-500">{svc.duration_minutes} min · ${svc.base_price}</div>
                </button>
              ))}
            </div>
            
            <h3 className="font-semibold mt-6 mb-4">Preferred Barber (Optional)</h3>
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => setSelectedBarberForAppt(null)}
                className={`px-4 py-2 rounded-lg ${!selectedBarberForAppt ? "bg-blue-600 text-white" : "bg-gray-100"}`}
              >
                Any
              </button>
              {barbers.map(b => (
                <button
                  key={b.id}
                  onClick={() => setSelectedBarberForAppt(b)}
                  className={`px-4 py-2 rounded-lg ${selectedBarberForAppt?.id === b.id ? "bg-blue-600 text-white" : "bg-gray-100"}`}
                >
                  {b.name}
                </button>
              ))}
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => { setShowAppointmentModal(false); resetBookingForm() }} className="flex-1 py-3 bg-gray-200 rounded-lg font-semibold">Cancel</button>
              <button
                onClick={() => { setBookingStep("time"); loadTimeSlots() }}
                disabled={!selectedServiceForAppt}
                className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-semibold disabled:bg-gray-300"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Select Time */}
        {bookingStep === "time" && (
          <div>
            <h3 className="font-semibold mb-4">Select Date & Time</h3>
            <input
              type="date"
              value={appointmentDate}
              onChange={e => { setAppointmentDate(e.target.value); setTimeout(loadTimeSlots, 100) }}
              className="w-full p-3 border rounded-lg mb-4"
            />
            
            <div className="grid grid-cols-4 gap-2 max-h-60 overflow-y-auto">
              {timeSlots.map(slot => (
                <button
                  key={slot.time}
                  onClick={() => setSelectedSlot(slot)}
                  className={`p-3 rounded-lg text-center ${
                    selectedSlot?.time === slot.time
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 hover:bg-gray-200"
                  }`}
                >
                  {slot.time}
                </button>
              ))}
            </div>
            
            {timeSlots.length === 0 && (
              <p className="text-center text-gray-500 py-8">No available slots for this date</p>
            )}

            <div className="flex gap-3 mt-6">
              <button onClick={() => setBookingStep("service")} className="flex-1 py-3 bg-gray-200 rounded-lg font-semibold">Back</button>
              <button
                onClick={() => setBookingStep("details")}
                disabled={!selectedSlot}
                className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-semibold disabled:bg-gray-300"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Customer Details */}
        {bookingStep === "details" && (
          <div>
            <h3 className="font-semibold mb-4">Customer Information</h3>
            
            <div className="bg-blue-50 rounded-lg p-4 mb-4">
              <p className="font-semibold">{selectedServiceForAppt?.name}</p>
              <p className="text-sm text-gray-600">
                {new Date(selectedSlot?.datetime || "").toLocaleString()} 
                {selectedBarberForAppt && ` with ${selectedBarberForAppt.name}`}
              </p>
            </div>
            
            <div className="space-y-4">
              <input
                type="text"
                placeholder="Customer Name *"
                value={apptCustomerName}
                onChange={e => setApptCustomerName(e.target.value)}
                className="w-full p-3 border rounded-lg"
              />
              <input
                type="tel"
                placeholder="Phone Number *"
                value={apptCustomerPhone}
                onChange={e => setApptCustomerPhone(e.target.value)}
                className="w-full p-3 border rounded-lg"
              />
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setBookingStep("time")} className="flex-1 py-3 bg-gray-200 rounded-lg font-semibold">Back</button>
              <button
                onClick={bookAppointment}
                disabled={!apptCustomerName || !apptCustomerPhone}
                className="flex-1 py-3 bg-green-600 text-white rounded-lg font-semibold disabled:bg-gray-300"
              >
                Book Appointment
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )

  // Appointments View
  const AppointmentsView = () => (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold">📅 Appointments</h2>
          <div className="flex items-center gap-4">
            <input
              type="date"
              value={appointmentDate}
              onChange={e => setAppointmentDate(e.target.value)}
              className="px-4 py-2 border-2 rounded-lg"
            />
            <button
              onClick={() => setShowAppointmentModal(true)}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg font-bold hover:bg-blue-700"
            >
              ➕ Book New
            </button>
          </div>
        </div>
      </div>

      {appointments.length === 0 ? (
        <div className="bg-white rounded-xl shadow-lg p-12 text-center text-gray-500">
          No appointments for this date
        </div>
      ) : (
        <div className="space-y-4">
          {appointments.map(appt => (
            <div key={appt.id} className={`bg-white rounded-xl shadow-lg p-6 border-l-4 ${
              appt.status === "completed" ? "border-green-500" :
              appt.status === "in_progress" ? "border-blue-500" :
              appt.status === "cancelled" ? "border-red-500" : "border-yellow-500"
            }`}>
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold">
                      {new Date(appt.scheduled_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className="font-semibold">{appt.customer_name}</span>
                    <span className={`px-2 py-1 rounded text-xs font-bold ${
                      appt.status === "completed" ? "bg-green-100 text-green-800" :
                      appt.status === "in_progress" ? "bg-blue-100 text-blue-800" :
                      appt.status === "cancelled" ? "bg-red-100 text-red-800" :
                      "bg-yellow-100 text-yellow-800"
                    }`}>
                      {appt.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-gray-600">{appt.service_name} ({appt.duration_minutes} min)</p>
                  {appt.barber_name && <p className="text-sm text-blue-600">Barber: {appt.barber_name}</p>}
                  <p className="text-sm text-gray-500">{appt.customer_phone}</p>
                </div>
                {appt.status === "scheduled" && (
                  <button
                    onClick={() => cancelAppointment(appt.id)}
                    className="px-4 py-2 bg-red-100 text-red-600 rounded-lg font-semibold hover:bg-red-200"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  // Product Checkout Modal
  const ProductCheckoutModal = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">
        <h2 className="text-2xl font-bold mb-6">🛍️ Product Sale</h2>
        
        <div className="space-y-3 mb-6 max-h-60 overflow-y-auto">
          {productCart.map((cp, i) => (
            <div key={i} className="flex justify-between items-center bg-gray-50 p-3 rounded-lg">
              <div>
                <div className="font-semibold">{cp.product.name}</div>
                <div className="text-sm text-gray-500">${cp.product.price} × {cp.quantity}</div>
              </div>
              <span className="font-bold">${(cp.product.price * cp.quantity).toFixed(2)}</span>
            </div>
          ))}
        </div>
        
        <div className="border-t pt-4 space-y-2">
          <div className="flex justify-between">
            <span>Subtotal</span>
            <span>${productSubtotal.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span>Tax</span>
            <span>${productTax.toFixed(2)}</span>
          </div>
          <div className="flex justify-between text-xl font-bold">
            <span>Total</span>
            <span className="text-green-600">${productTotal.toFixed(2)}</span>
          </div>
        </div>
        
        <div className="flex gap-3 mt-6">
          <button onClick={() => setShowProductCheckout(false)} className="flex-1 py-3 bg-gray-200 rounded-lg font-bold">Cancel</button>
          <button onClick={processProductSale} className="flex-1 py-3 bg-green-600 text-white rounded-lg font-bold">Complete Sale</button>
        </div>
      </div>
    </div>
  )

  // Shop View
  const ShopView = () => {
    const PRODUCT_CATEGORIES = [
      { id: "styling", label: "💇 Styling" },
      { id: "beard", label: "🧔 Beard" },
      { id: "haircare", label: "🧴 Hair Care" },
      { id: "shaving", label: "🪒 Shaving" },
      { id: "tools", label: "✂️ Tools" },
    ]
    
    const filteredProducts = products.filter(p => p.category === selectedProductCategory)
    
    return (
      <div className="flex h-[calc(100vh-80px)]">
        {/* Products Grid */}
        <div className="flex-1 flex flex-col bg-gray-50">
          <div className="flex gap-2 p-4 bg-white border-b overflow-x-auto">
            {PRODUCT_CATEGORIES.map(cat => (
              <button
                key={cat.id}
                onClick={() => setSelectedProductCategory(cat.id)}
                className={`px-4 py-2 rounded-lg font-semibold whitespace-nowrap ${
                  selectedProductCategory === cat.id ? "bg-blue-600 text-white" : "bg-gray-100"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
          
          <div className="flex-1 overflow-auto p-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {filteredProducts.map(product => (
                <button
                  key={product.id}
                  onClick={() => addToProductCart(product)}
                  disabled={product.stock === 0}
                  className={`bg-white rounded-xl shadow p-4 text-left hover:shadow-lg transition ${
                    product.stock === 0 ? "opacity-50" : "border-2 border-transparent hover:border-blue-300"
                  }`}
                >
                  <h3 className="font-bold text-gray-800">{product.name}</h3>
                  <p className="text-sm text-gray-500">Stock: {product.stock}</p>
                  <p className="text-xl font-bold text-green-600 mt-2">${product.price.toFixed(2)}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
        
        {/* Cart */}
        <div className="w-80 bg-white border-l flex flex-col">
          <div className="p-4 border-b">
            <h2 className="text-xl font-bold">🛒 Cart</h2>
          </div>
          
          <div className="flex-1 overflow-auto p-4">
            {productCart.length === 0 ? (
              <p className="text-center text-gray-400 py-8">Cart is empty</p>
            ) : (
              <div className="space-y-3">
                {productCart.map((cp, i) => (
                  <div key={i} className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                    <div>
                      <div className="font-semibold">{cp.product.name}</div>
                      <div className="text-sm text-gray-500">${cp.product.price} × {cp.quantity}</div>
                    </div>
                    <button onClick={() => removeFromProductCart(i)} className="text-red-500">✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div className="p-4 border-t bg-gray-50">
            <div className="flex justify-between text-xl font-bold mb-4">
              <span>Total</span>
              <span>${productSubtotal.toFixed(2)}</span>
            </div>
            <button
              onClick={() => setShowProductCheckout(true)}
              disabled={productCart.length === 0}
              className="w-full py-4 bg-green-600 text-white rounded-xl font-bold disabled:bg-gray-300"
            >
              Checkout
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Reports View
  const ReportsView = () => (
    <div className="max-w-6xl mx-auto space-y-6">
      {dailyReport && (
        <div className="bg-white rounded-xl shadow-lg p-6">
          <h2 className="text-2xl font-bold mb-4">📊 Today's Summary</h2>
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-green-600">
                ${dailyReport.summary.total_revenue.toFixed(0)}
              </div>
              <div className="text-sm text-gray-600">Revenue</div>
            </div>
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-blue-600">
                {dailyReport.summary.num_customers}
              </div>
              <div className="text-sm text-gray-600">Customers</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-purple-600">
                ${dailyReport.summary.total_tips.toFixed(0)}
              </div>
              <div className="text-sm text-gray-600">Tips</div>
            </div>
            <div className="bg-amber-50 rounded-lg p-4 text-center">
              <div className="text-3xl font-bold text-amber-600">
                ${dailyReport.summary.average_ticket.toFixed(0)}
              </div>
              <div className="text-sm text-gray-600">Avg Ticket</div>
            </div>
          </div>
        </div>
      )}

      {earningsReport && (
        <div className="bg-white rounded-xl shadow-lg p-6">
          <h2 className="text-2xl font-bold mb-4">💰 Barber Earnings (This Month)</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left">Barber</th>
                  <th className="px-4 py-3 text-left">Services</th>
                  <th className="px-4 py-3 text-left">Revenue</th>
                  <th className="px-4 py-3 text-left">Commission</th>
                  <th className="px-4 py-3 text-left">Tips</th>
                  <th className="px-4 py-3 text-left">Total Earnings</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {earningsReport.barbers.map((b: any) => (
                  <tr key={b.barber_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-semibold">{b.barber_name}</td>
                    <td className="px-4 py-3">{b.total_services}</td>
                    <td className="px-4 py-3">${b.total_revenue.toFixed(2)}</td>
                    <td className="px-4 py-3">${b.commission_earned.toFixed(2)}</td>
                    <td className="px-4 py-3 text-green-600">${b.tips_earned.toFixed(2)}</td>
                    <td className="px-4 py-3 font-bold text-blue-600">${b.total_earnings.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-gray-50 font-bold">
                <tr>
                  <td className="px-4 py-3">TOTAL</td>
                  <td className="px-4 py-3">-</td>
                  <td className="px-4 py-3">${earningsReport.totals.total_revenue.toFixed(2)}</td>
                  <td className="px-4 py-3">${earningsReport.totals.total_commission.toFixed(2)}</td>
                  <td className="px-4 py-3">${earningsReport.totals.total_tips.toFixed(2)}</td>
                  <td className="px-4 py-3 text-blue-600">${earningsReport.totals.total_earnings.toFixed(2)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </div>
  )

  // Main POS View
  const POSView = () => (
    <div className="flex h-screen">
      {/* Left Panel - Services */}
      <div className="flex-1 flex flex-col bg-gray-50">
        {/* Categories */}
        <div className="flex gap-2 p-4 bg-white border-b overflow-x-auto">
          {CATEGORIES.map(cat => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-4 py-2 rounded-lg font-semibold whitespace-nowrap transition ${
                selectedCategory === cat.id
                  ? `bg-${cat.color}-600 text-white`
                  : "bg-gray-100 hover:bg-gray-200"
              }`}
              style={{
                backgroundColor: selectedCategory === cat.id ? 
                  (cat.color === "blue" ? "#2563eb" : 
                   cat.color === "amber" ? "#d97706" :
                   cat.color === "green" ? "#16a34a" : "#9333ea") : undefined,
                color: selectedCategory === cat.id ? "white" : undefined
              }}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Services Grid */}
        <div className="flex-1 overflow-auto p-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {filteredServices.map(service => (
              <button
                key={service.id}
                onClick={() => addService(service)}
                className="bg-white rounded-xl shadow p-4 text-left hover:shadow-lg transition border-2 border-transparent hover:border-blue-300"
              >
                <h3 className="font-bold text-gray-800">{service.name}</h3>
                <p className="text-sm text-gray-500">{service.duration_minutes} min</p>
                <p className="text-xl font-bold text-blue-600 mt-2">
                  ${service.base_price.toFixed(2)}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Right Panel - Cart */}
      <div className="w-96 bg-white border-l flex flex-col">
        {/* Customer & Barber */}
        <div className="p-4 border-b space-y-3">
          {/* Customer search */}
          <div>
            <label className="text-sm font-semibold text-gray-600">Customer</label>
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <input
                  type="tel"
                  placeholder="Search by phone..."
                  value={customerPhone}
                  onChange={e => handlePhoneChange(e.target.value)}
                  className="w-full p-2 border rounded-lg"
                />
                {customers.length > 0 && !customer && (
                  <div className="absolute top-full left-0 right-0 bg-white border rounded-lg shadow-lg z-10 max-h-40 overflow-auto">
                    {customers.map(c => (
                      <button
                        key={c.id}
                        onClick={() => { setCustomer(c); setCustomerPhone(c.phone); setCustomers([]) }}
                        className="w-full p-2 text-left hover:bg-gray-50"
                      >
                        {c.name} - {c.phone}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => { setNewCustomerPhone(customerPhone); setShowNewCustomerModal(true) }}
                className="px-3 py-2 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                ➕
              </button>
            </div>
            {customer && (
              <div className="mt-2 p-2 bg-blue-50 rounded-lg flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{customer.name}</span>
                  <span className="text-sm text-gray-500">{customer.phone}</span>
                  <button
                    onClick={() => fetchCustomerProfile(customer.id)}
                    className="text-blue-600 hover:text-blue-800 text-sm underline"
                  >
                    View History
                  </button>
                </div>
                <button onClick={() => { setCustomer(null); setCustomerPhone("") }} className="text-red-500">✕</button>
              </div>
            )}
          </div>

          {/* Barber selection */}
          <div>
            <label className="text-sm font-semibold text-gray-600">Barber</label>
            <div className="flex gap-2 mt-1 overflow-x-auto pb-2">
              {barbers.map(b => (
                <button
                  key={b.id}
                  onClick={() => setSelectedBarber(b)}
                  className={`px-3 py-2 rounded-lg whitespace-nowrap font-semibold transition ${
                    selectedBarber?.id === b.id
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 hover:bg-gray-200"
                  }`}
                >
                  {b.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Cart Items */}
        <div className="flex-1 overflow-auto p-4">
          {orderServices.length === 0 ? (
            <div className="text-center text-gray-400 py-8">
              Tap services to add
            </div>
          ) : (
            <div className="space-y-3">
              {orderServices.map((os, index) => (
                <div key={index} className="bg-gray-50 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="font-semibold">{os.service.name}</div>
                      <div className="text-sm text-gray-500">
                        ${os.service.base_price.toFixed(2)} × {os.quantity}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold">
                        ${(os.service.base_price * os.quantity).toFixed(2)}
                      </span>
                      <button
                        onClick={() => removeService(index)}
                        className="p-1 text-red-500 hover:bg-red-50 rounded"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                  <input
                    type="text"
                    placeholder="Add notes (e.g., fade style, length)..."
                    value={os.notes || ""}
                    onChange={e => {
                      const updated = [...orderServices]
                      updated[index] = { ...os, notes: e.target.value }
                      setOrderServices(updated)
                    }}
                    className="w-full mt-2 p-2 text-sm border rounded bg-white"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Totals & Checkout */}
        <div className="p-4 border-t bg-gray-50">
          <div className="space-y-2 mb-4">
            <div className="flex justify-between text-gray-600">
              <span>Subtotal</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>Tax (8.75%)</span>
              <span>${tax.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-xl font-bold">
              <span>Total</span>
              <span>${(subtotal + tax).toFixed(2)}</span>
            </div>
          </div>

          <button
            onClick={() => setShowPaymentModal(true)}
            disabled={orderServices.length === 0}
            className="w-full py-4 bg-green-600 text-white rounded-xl font-bold text-lg hover:bg-green-700 disabled:bg-gray-300"
          >
            Checkout
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Navigation */}
      <nav className="bg-slate-800 text-white p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-bold">💈 Barbershop POS</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowFeedbackModal(true)}
              className="px-3 py-2 bg-slate-700 rounded-lg hover:bg-slate-600"
              title="Send Feedback"
            >
              📝
            </button>
            <button
              onClick={() => { loadDrawerStatus(); setShowCashDrawer(true) }}
              className="px-3 py-2 bg-slate-700 rounded-lg hover:bg-slate-600"
              title="Cash Drawer"
            >
              💰
            </button>
            <button
              onClick={() => { refreshBarbers(); setShowBarberPanel(true) }}
              className="px-3 py-2 bg-slate-700 rounded-lg hover:bg-slate-600 mr-4"
              title="Barber Management"
            >
              👔 Staff
            </button>
            {[
              { id: "pos", label: "✂️ POS" },
              { id: "queue", label: "📋 Queue" },
              { id: "appointments", label: "📅 Appts" },
              { id: "orders", label: "📝 Orders" },
              { id: "shop", label: "🛍️ Shop" },
              { id: "reports", label: "📊 Reports" },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setViewMode(tab.id as ViewMode)}
                className={`px-4 py-2 rounded-lg font-semibold transition ${
                  viewMode === tab.id
                    ? "bg-white text-slate-800"
                    : "hover:bg-slate-700"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className={viewMode === "pos" ? "" : "p-6"}>
        {viewMode === "pos" && <POSView />}
        {viewMode === "queue" && <QueueView />}
        {viewMode === "appointments" && <AppointmentsView />}
        {viewMode === "orders" && <OrdersView />}
        {viewMode === "shop" && <ShopView />}
        {viewMode === "reports" && <ReportsView />}
      </main>

      {/* Modals */}
      {showPaymentModal && <PaymentModal />}
      {showNewCustomerModal && <NewCustomerModal />}
      {showWalkInModal && <WalkInModal />}
      {showAppointmentModal && <AppointmentModal />}
      {showBarberPanel && <BarberPanel />}
      {showCustomerProfile && <CustomerProfileModal />}
      {showCashDrawer && <CashDrawerModal />}
      {showProductCheckout && <ProductCheckoutModal />}
      {showFeedbackModal && <FeedbackModal />}
    </div>
  )
}

export default App
