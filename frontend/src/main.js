import { createApp } from 'vue';
import PrimeVue from 'primevue/config';
import ToastService from 'primevue/toastservice';

import Button from 'primevue/button';
import Card from 'primevue/card';
import Checkbox from 'primevue/checkbox';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dialog from 'primevue/dialog';
import Divider from 'primevue/divider';
import Dropdown from 'primevue/dropdown';
import FileUpload from 'primevue/fileupload';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import ProgressBar from 'primevue/progressbar';
import Slider from 'primevue/slider';
import TabPanel from 'primevue/tabpanel';
import TabView from 'primevue/tabview';
import Textarea from 'primevue/textarea';
import Toast from 'primevue/toast';

import 'primevue/resources/themes/lara-dark-blue/theme.css';
import 'primevue/resources/primevue.min.css';
import 'primeicons/primeicons.css';
import './styles.css';

import App from './App.vue';

const app = createApp(App);

app.use(PrimeVue, { ripple: true });
app.use(ToastService);

app.component('Button', Button);
app.component('Card', Card);
app.component('Checkbox', Checkbox);
app.component('Column', Column);
app.component('DataTable', DataTable);
app.component('Dialog', Dialog);
app.component('Divider', Divider);
app.component('Dropdown', Dropdown);
app.component('FileUpload', FileUpload);
app.component('InputText', InputText);
app.component('Password', Password);
app.component('ProgressBar', ProgressBar);
app.component('Slider', Slider);
app.component('TabPanel', TabPanel);
app.component('TabView', TabView);
app.component('Textarea', Textarea);
app.component('Toast', Toast);

app.mount('#app');
