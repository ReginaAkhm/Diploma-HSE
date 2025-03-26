import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date, timedelta
from io import BytesIO
import psycopg2

st.set_page_config(layout="wide")
st.title("Hotel Chain Booking Forecast")

try:
    conn = psycopg2.connect(
            dbname="Hotel_Chain_Bookings",
            host="localhost",
            port="5432"
        )
    
    go_calc = True
    
except:
    st.markdown(f"**Database unavailable, try again later...**")
    go_calc = False

if go_calc == True:

    hotel_room_map = pd.read_sql("select m.object_id, h.name as hotel_name, m.room_type_agg_id, r.name as room_name from hotel_room_map as m\
                          join hotels as h\
                          on m.object_id = h.object_id\
                            join rooms as r\
                                 on m.room_type_agg_id = r.room_type_agg_id;", conn)
    
    unique_hotels = hotel_room_map[['object_id', 'hotel_name']].drop_duplicates()
    unique_rooms = hotel_room_map[['room_type_agg_id', 'room_name']].drop_duplicates()
    hotel_name_to_id = {row['hotel_name']: row['object_id'] for _, row in unique_hotels.iterrows()}
    id_to_hotel_name = {v: k for k, v in hotel_name_to_id.items()}
    room_name_to_id = {row['room_name']: row['room_type_agg_id'] for _, row in unique_rooms.iterrows()}
    id_to_room_name = {v: k for k, v in room_name_to_id.items()}

    days = st.slider("Number of forecast days", 1, 30, 7)
    start_date = date.today()
    st.markdown(f"**Start Date:** {start_date.strftime('%Y-%m-%d')}")

    end_date = start_date + timedelta(days=days)
    st.markdown(f"**End Date:** {end_date.strftime('%Y-%m-%d')}")

    hotels_names = st.multiselect(
            "Select hotels",
            options=list(hotel_name_to_id.keys()),
            default=[list(hotel_name_to_id.keys())[0]]
        )

    hotels_id = [hotel_name_to_id[name] for name in hotels_names]

    view_mode = st.radio(
        "Forecast mode",
        ["By hotels", "By hotels and room types"]
    )

    room_types_names = (
            hotel_room_map.groupby('hotel_name')['room_name']
            .unique() 
            .apply(list)
            .to_dict()
        )
    
    room_types_id = {} 
    for hotel_name, rooms in room_types_names.items():
        hotel_id = hotel_name_to_id[hotel_name]
        room_ids = [room_name_to_id[room] for room in rooms]
        room_types_id[hotel_id] = room_ids


    selected_rooms = {} 
    if view_mode == "By hotels and room types" and hotels_names:
        for hotel in hotels_names:
            selected_rooms[hotel] = st.multiselect(
                f"Room types for hotel {hotel}",
                options=room_types_names[hotel],
                default=room_types_names[hotel]
            )
    
    result_dict = {} 
    for hotel_name, rooms in selected_rooms.items():
        hotel_id = hotel_name_to_id[hotel_name]
        room_ids = [room_name_to_id[room] for room in rooms]
        result_dict[hotel_id] = room_ids

    @st.cache_data(show_spinner=True)
    def get_forecast(start_date, end_date, hotels_id, view_mode, selected_rooms_param):
        selected = {hotel: list(rooms) for hotel, rooms in selected_rooms_param}

        date_range = pd.date_range(start_date, end_date)
        forecasts = []
        for hotel in hotels_id:
            for room in room_types_id[hotel]:
                for dt in date_range:
                    forecasts.append({
                        'date': dt,
                        'hotel': hotel,
                        'hotel_name': id_to_hotel_name[hotel],
                        'room_type': room,
                        'room_type_name': id_to_room_name[room],
                        'forecast': np.random.randint(50, 100)
                    })
        forecast_df = pd.DataFrame(forecasts)
        
        filtered_df = forecast_df[forecast_df['hotel'].isin(hotels_id)]
        
        if view_mode == "By hotels":
            processed_df = filtered_df.groupby(['date', 'hotel', 'hotel_name'])['forecast'].mean().reset_index()
        else:
            processed_df = filtered_df[filtered_df.apply(
                lambda x: x['room_type'] in selected.get(x['hotel'], []),
                axis=1
            )]
        
        return processed_df

    if st.button("Get forecast"):
        selected_rooms_param = \
            tuple((hotel, tuple(rooms)) for hotel, rooms in result_dict.items()) if view_mode == "By hotels and room types" else tuple()
        
        st.session_state.forecast_data = get_forecast(
            start_date, end_date, hotels_id, view_mode, selected_rooms_param
        )
        st.session_state.forecast_params = {
            'hotels': hotels_id.copy(),
            'view_mode': view_mode
        }

    if 'forecast_data' in st.session_state:
        st.header("Booking forecast")
        
        for hotel in st.session_state.forecast_params['hotels']:
            hotel_data = st.session_state.forecast_data[
                st.session_state.forecast_data['hotel'] == hotel
            ]
            
            if st.session_state.forecast_params['view_mode'] == "By hotels":
                fig = px.line(
                    hotel_data,
                    x='date',
                    y='forecast',
                    title=f"Forecast of the number of bookings for the {id_to_hotel_name[hotel]} hotel",
                    labels={'forecast': 'number of bookings'},
                    height=400
                )
            else:
                fig = px.line(
                    hotel_data,
                    x='date',
                    y='forecast',
                    color='room_type_name',
                    title=f"Forecast of the number of bookings for the {id_to_hotel_name[hotel]} hotel - by room types",
                    labels={'forecast': 'number of bookings'},
                    height=400
                )
            
            fig.update_traces(mode="markers+lines", hovertemplate="Date: %{x}<br>Number of bookings %{y}")
            fig.update_layout(
                hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)

    # Кнопка выгрузки
    if 'forecast_data' in st.session_state:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            st.session_state.forecast_data.to_excel(writer, index=False)
        
        st.download_button(
            label="Download in Excel",
            data=output.getvalue(),
            file_name=f'hotel_forecast_{date.today()}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
